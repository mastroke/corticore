"""End-to-end orchestrator tests with a fake cloud client + in-memory ledger."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from conftest import FakeCloudClient, make_result_text  # noqa: E402
from swarm.config import parse_config  # noqa: E402
from swarm.ledger import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    InMemoryLedger,
    LedgerEntry,
    find_resumable,
)
from swarm.orchestrator import Orchestrator  # noqa: E402
from swarm.runner import CloudRunResult, SwarmRunner  # noqa: E402

PROMPTS_DIR = REPO_ROOT / "orchestrate" / "prompts"


def _config():
    data = {
        "roles": {
            "maintenance_scout": {"model": "gpt-5.6-sol", "prompt_file": "swarm/maintenance_scout.md"},
            "research_scout": {"model": "gpt-5.6-sol", "prompt_file": "swarm/research_scout.md"},
            "release_risk_critic": {"model": "gpt-5.6-sol", "prompt_file": "swarm/release_risk_critic.md"},
            "judge": {"model": "gpt-5.6-sol", "prompt_file": "swarm/judge.md"},
            "executor": {
                "model": "composer-2.5",
                "prompt_file": "swarm/executor.md",
                "can_write": True,
                "auto_create_pr": True,
            },
        },
        "tasks": [
            {
                "name": "corticore-maintenance",
                "description": "keep it healthy",
                "repo": "o/r",
                "thinker_roles": ["maintenance_scout", "research_scout", "release_risk_critic"],
                "judge_role": "judge",
                "executor_role": "executor",
            }
        ],
    }
    return parse_config(data)


def _finished(text, agent_id="bc-x", pr_url=None):
    return CloudRunResult(agent_id=agent_id, run_id="r", status="finished", text=text, pr_url=pr_url)


def _replies(judge_execute=True, chosen="Fix CI"):
    scout_text = make_result_text(
        "ok", "found work", {"proposals": [{"title": "Fix CI", "priority": 5}]}
    )
    empty_text = make_result_text("ok", "nothing", {"proposals": []})
    judge_data = (
        {"execute": True, "chosen_title": chosen, "scope": "repair CI", "acceptance_criteria": ["green"]}
        if judge_execute
        else {"execute": False, "reason": "quiet"}
    )
    return {
        "maintenance_scout": _finished(scout_text),
        "research_scout": _finished(empty_text),
        "release_risk_critic": _finished(empty_text),
        "judge": _finished(make_result_text("execute", "chosen", judge_data)),
        "executor": _finished(
            make_result_text("done", "opened PR", {"pr_url": "https://github.com/o/r/pull/1"}),
            agent_id="bc-exec",
            pr_url="https://github.com/o/r/pull/1",
        ),
    }


def _orchestrator(replies, write_enabled, ledger=None):
    client = FakeCloudClient(replies)
    runner = SwarmRunner(client, clock=lambda: 0.0, sleep=lambda s: None)
    ledger = ledger or InMemoryLedger()
    orch = Orchestrator(_config(), runner, ledger, PROMPTS_DIR, write_enabled=write_enabled)
    return orch, client, ledger


def test_cycle_runs_thinkers_and_judge_and_executes():
    orch, client, ledger = _orchestrator(_replies(), write_enabled=True)
    report = orch.run_cycle("corticore-maintenance", deadline=None)

    assert len(report.thinker_outcomes) == 3
    assert report.plan.execute is True
    assert report.executed() is True
    assert report.pr_url == "https://github.com/o/r/pull/1"
    # executor must be the only write-capable call, with auto_create_pr set.
    exec_calls = [c for c in client.calls if c["role"] == "executor"]
    assert exec_calls and exec_calls[0]["auto_create_pr"] is True


def test_write_disabled_skips_executor():
    orch, client, ledger = _orchestrator(_replies(), write_enabled=False)
    report = orch.run_cycle("corticore-maintenance", deadline=None)

    assert report.plan.execute is True
    assert report.executor_outcome is None
    assert "write disabled" in report.skipped_reason
    assert all(c["role"] != "executor" for c in client.calls)
    # A blocked ledger entry documents that a plan was chosen but not run.
    assert any(e.status == "blocked" for e in ledger.entries())


def test_judge_hold_means_no_execution():
    orch, _client, _ledger = _orchestrator(_replies(judge_execute=False), write_enabled=True)
    report = orch.run_cycle("corticore-maintenance", deadline=None)
    assert report.plan.execute is False
    assert report.executor_outcome is None


def test_ledger_records_in_progress_before_completion():
    orch, _client, ledger = _orchestrator(_replies(), write_enabled=True)
    orch.run_cycle("corticore-maintenance", deadline=None)
    statuses = [e.status for e in ledger.entries() if e.role == "executor"]
    assert STATUS_IN_PROGRESS in statuses
    assert STATUS_COMPLETED in statuses
    # in_progress must precede completed.
    assert statuses.index(STATUS_IN_PROGRESS) < statuses.index(STATUS_COMPLETED)


def test_resumes_prior_in_progress_executor():
    ledger = InMemoryLedger()
    ledger.record(
        LedgerEntry(
            cycle_id="old",
            task="corticore-maintenance",
            role="executor",
            status=STATUS_IN_PROGRESS,
            summary="interrupted",
            agent_id="bc-prev",
        )
    )
    assert find_resumable(ledger, "corticore-maintenance") is not None

    orch, client, _ledger = _orchestrator(_replies(), write_enabled=True, ledger=ledger)
    orch.run_cycle("corticore-maintenance", deadline=None)
    assert "bc-prev" in client.resumed
