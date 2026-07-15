"""Tests for pure planning logic (proposal extraction + judge decision)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.planning import Proposal, decide_plan, extract_proposals  # noqa: E402
from swarm.results import AgentResult  # noqa: E402
from swarm.runner import RoleOutcome  # noqa: E402


def _thinker(role, proposals):
    result = AgentResult(verdict="ok", summary="s", data={"proposals": proposals})
    return RoleOutcome(role=role, status="finished", result=result)


def _judge(data):
    result = AgentResult(verdict="execute", summary="s", data=data)
    return RoleOutcome(role="judge", status="finished", result=result)


def test_extract_proposals_collects_valid_entries():
    outcomes = [
        _thinker("scout", [{"title": "Fix CI", "priority": 5, "kind": "maintenance"}]),
        _thinker("research", [{"title": "Add decay note", "rationale": "r"}]),
    ]
    proposals = extract_proposals(outcomes)
    titles = {p.title for p in proposals}
    assert titles == {"Fix CI", "Add decay note"}


def test_extract_proposals_skips_malformed_and_failed():
    failed = RoleOutcome(role="x", status="error", error="boom")
    bad = _thinker("scout", [{"no_title": 1}, "not a dict"])
    proposals = extract_proposals([failed, bad])
    assert proposals == []


def test_decide_plan_executes_matching_proposal():
    proposals = [Proposal(title="Fix CI", rationale="r", priority=5)]
    judge = _judge(
        {
            "execute": True,
            "chosen_title": "Fix CI",
            "scope": "repair the workflow",
            "acceptance_criteria": ["ci green"],
        }
    )
    plan = decide_plan(judge, proposals)
    assert plan.execute is True
    assert plan.proposal.title == "Fix CI"
    assert plan.acceptance_criteria == ["ci green"]


def test_decide_plan_holds_when_judge_holds():
    judge = _judge({"execute": False, "reason": "quiet day"})
    plan = decide_plan(judge, [])
    assert plan.execute is False
    assert "quiet day" in plan.reason


def test_decide_plan_holds_when_chosen_title_unmatched():
    proposals = [Proposal(title="A")]
    judge = _judge({"execute": True, "chosen_title": "Nonexistent"})
    plan = decide_plan(judge, proposals)
    assert plan.execute is False
    assert "did not match" in plan.reason


def test_decide_plan_holds_when_judge_failed():
    failed = RoleOutcome(role="judge", status="error", error="boom")
    plan = decide_plan(failed, [Proposal(title="A")])
    assert plan.execute is False


def test_decide_plan_holds_when_no_judge():
    plan = decide_plan(None, [Proposal(title="A")])
    assert plan.execute is False
