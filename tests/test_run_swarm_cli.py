"""Tests for the run_swarm CLI wiring (dry-run, kill switch, guards)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

import run_swarm  # noqa: E402


def test_kill_switch_enabled_variants():
    assert run_swarm.kill_switch_enabled({"SWARM_ENABLED": "true"}) is True
    assert run_swarm.kill_switch_enabled({"SWARM_ENABLED": "TRUE"}) is True
    assert run_swarm.kill_switch_enabled({"SWARM_ENABLED": "false"}) is False
    assert run_swarm.kill_switch_enabled({}) is False


def test_dry_run_prints_prompts_without_api_key():
    pytest.importorskip("yaml")
    exit_code = run_swarm.main(["--dry-run", "--task", "corticore-maintenance"], env={})
    assert exit_code == 0


def test_dry_run_captures_all_roles(capsys):
    pytest.importorskip("yaml")
    run_swarm.main(["--dry-run"], env={})
    out = capsys.readouterr().out
    assert "ROLE: maintenance_scout" in out
    assert "ROLE: executor" in out
    assert "no agents launched" in out


def test_live_run_without_api_key_fails_fast():
    pytest.importorskip("yaml")
    exit_code = run_swarm.main([], env={})
    assert exit_code == 1


class _ClosedWindow:
    """Stand-in OperatingWindow that is always closed."""

    def __init__(self, **_kwargs):
        pass

    def now_local(self, *_a, **_k):
        return 0

    def is_open(self, _now):
        return False

    def seconds_until_close(self, _now):
        return 0.0


class _FakeReport:
    cycle_id = "cycle-test"
    task = "corticore-maintenance"
    thinker_outcomes = []
    proposals = []
    plan = None
    skipped_reason = None
    pr_url = None
    executor_outcome = None

    def executed(self):
        return False


def _patch_live_deps(monkeypatch, calls):
    """Stub out every network/side-effecting seam so main() can run offline."""
    monkeypatch.setattr(run_swarm, "list_available_model_ids", lambda _key: [])
    monkeypatch.setattr(run_swarm, "validate_models", lambda _req, _avail: None)
    monkeypatch.setattr(run_swarm, "OperatingWindow", _ClosedWindow)
    monkeypatch.setattr(run_swarm, "SwarmRunner", lambda _client: object())
    monkeypatch.setattr(run_swarm, "_build_ledger", lambda _args, _env: object())

    import swarm.cursor_client as cc

    monkeypatch.setattr(cc, "CursorCloudClient", lambda **_k: object())

    class _FakeOrchestrator:
        def __init__(self, *_a, **_k):
            pass

        def run_cycle(self, task, deadline):
            calls["run_cycle"] = {"task": task, "deadline": deadline}
            return _FakeReport()

    monkeypatch.setattr(run_swarm, "Orchestrator", _FakeOrchestrator)


def test_closed_window_skips_without_ignore_flag(monkeypatch):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls)
    exit_code = run_swarm.main([], env={"CURSOR_API_KEY": "k"})
    assert exit_code == 0
    assert "run_cycle" not in calls  # window closed -> no work started


def test_ignore_window_runs_cycle_when_closed(monkeypatch):
    pytest.importorskip("yaml")
    calls = {}
    _patch_live_deps(monkeypatch, calls)
    exit_code = run_swarm.main(
        ["--no-write", "--ignore-window"], env={"CURSOR_API_KEY": "k"}
    )
    assert exit_code == 0
    assert "run_cycle" in calls  # bypassed the closed window and ran
