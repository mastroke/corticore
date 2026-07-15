"""Pure planning logic: turn thinker findings + a judge verdict into a plan.

Thinkers each emit a list of candidate proposals; the judge picks at most one
to execute this cycle. This module normalizes their machine-readable output
into typed objects and applies the selection rule. It's deliberately pure so
the "what should we do today?" decision is unit-testable and auditable
separately from the side-effecting run machinery.

Authority split: the judge chooses *which* bounded task to do (agreement
among thinkers is advisory), but nothing here can bypass the deterministic
safety gates in `gates.py` - selection and permission are separate concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .results import AgentResult
from .runner import RoleOutcome


@dataclass(frozen=True)
class Proposal:
    """A single candidate task surfaced by a thinker."""

    title: str
    rationale: str = ""
    priority: int = 100  # lower = more important
    kind: str = "maintenance"
    source_role: str = ""


@dataclass(frozen=True)
class Plan:
    """The judge's decision for a cycle."""

    execute: bool
    proposal: Optional[Proposal]
    scope: str = ""
    acceptance_criteria: List[str] = field(default_factory=list)
    reason: str = ""


def extract_proposals(outcomes: Sequence[RoleOutcome]) -> List[Proposal]:
    """Collect proposals from every successful thinker outcome.

    Each thinker's result `data` may carry a `proposals` list of
    `{title, rationale, priority, kind}` objects. Malformed individual
    proposals are skipped rather than aborting planning, but a title is
    required (a proposal with no title isn't actionable).
    """
    proposals: List[Proposal] = []
    for outcome in outcomes:
        if not outcome.ok or outcome.result is None:
            continue
        raw_list = outcome.result.data.get("proposals", [])
        if not isinstance(raw_list, list):
            continue
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            title = raw.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            proposals.append(
                Proposal(
                    title=title.strip(),
                    rationale=str(raw.get("rationale", "")).strip(),
                    priority=int(raw.get("priority", 100)),
                    kind=str(raw.get("kind", "maintenance")).strip() or "maintenance",
                    source_role=outcome.role,
                )
            )
    return proposals


def _match_proposal(title: str, proposals: Sequence[Proposal]) -> Optional[Proposal]:
    wanted = title.strip().lower()
    for proposal in proposals:
        if proposal.title.strip().lower() == wanted:
            return proposal
    return None


def decide_plan(
    judge_outcome: Optional[RoleOutcome], proposals: Sequence[Proposal]
) -> Plan:
    """Build the cycle's `Plan` from the judge's verdict and the proposals.

    Fail-safe defaults: if the judge failed, produced no result, or didn't
    positively choose an executable proposal, the plan is "do nothing" rather
    than guessing. Doing nothing is always a safe cycle.
    """
    if judge_outcome is None or not judge_outcome.ok or judge_outcome.result is None:
        return Plan(
            execute=False,
            proposal=None,
            reason="judge produced no usable verdict; skipping execution this cycle",
        )

    result: AgentResult = judge_outcome.result
    data = result.data
    execute = bool(data.get("execute", False))
    if not execute:
        return Plan(
            execute=False,
            proposal=None,
            reason=str(data.get("reason", "judge chose not to execute this cycle")),
        )

    chosen_title = data.get("chosen_title")
    proposal: Optional[Proposal] = None
    if isinstance(chosen_title, str) and chosen_title.strip():
        proposal = _match_proposal(chosen_title, proposals)

    if proposal is None:
        # The judge said execute but named nothing we can map to a proposal.
        return Plan(
            execute=False,
            proposal=None,
            reason=(
                "judge asked to execute but its chosen_title did not match any "
                "thinker proposal; skipping to stay safe"
            ),
        )

    criteria = data.get("acceptance_criteria", [])
    if not isinstance(criteria, list):
        criteria = []

    return Plan(
        execute=True,
        proposal=proposal,
        scope=str(data.get("scope", "")).strip(),
        acceptance_criteria=[str(c) for c in criteria],
        reason=str(data.get("reason", "")).strip(),
    )
