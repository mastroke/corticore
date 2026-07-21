"""The cycle orchestrator: think in parallel, judge, execute at most once.

Ties the pure pieces (config, prompts, planning, gates) to the side-effecting
ones (runner, ledger) into one auditable cycle:

1. Run the task's thinker roles in parallel (bounded by the budget).
2. Collect their proposals and let the judge choose at most one.
3. If (and only if) the judge chose to execute, code-writing is enabled, and
   the budget/window allow it, run the single executor role to open a PR.
4. Record every step to the ledger so an interrupted cycle is resumable.

The orchestrator never merges, publishes, or overrides a safety gate; it
produces a PR and an audit trail. Verification and release are separate,
independently-gated workflows.
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .config import RoleConfig, SwarmConfig, TaskConfig
from .ledger import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    Ledger,
    LedgerEntry,
    find_resumable,
)
from .planning import Plan, Proposal, decide_plan, extract_proposals
from .prompts import assemble_prompt, load_prompt
from .runner import RoleOutcome, SwarmRunner


@dataclass
class CycleReport:
    cycle_id: str
    task: str
    thinker_outcomes: List[RoleOutcome] = field(default_factory=list)
    judge_outcome: Optional[RoleOutcome] = None
    executor_outcome: Optional[RoleOutcome] = None
    plan: Optional[Plan] = None
    proposals: List[Proposal] = field(default_factory=list)
    skipped_reason: Optional[str] = None
    pr_url: Optional[str] = None

    def executed(self) -> bool:
        return self.executor_outcome is not None and self.executor_outcome.ok


class Orchestrator:
    def __init__(
        self,
        config: SwarmConfig,
        runner: SwarmRunner,
        ledger: Ledger,
        prompts_dir: Path,
        *,
        write_enabled: bool = False,
    ) -> None:
        self._config = config
        self._runner = runner
        self._ledger = ledger
        self._prompts_dir = Path(prompts_dir)
        self._write_enabled = write_enabled

    # -- prompt/context helpers -------------------------------------------

    def _role(self, name: str) -> RoleConfig:
        return self._config.roles[name]

    def _base_context(self, task: TaskConfig, cycle_id: str) -> Dict:
        return {
            "cycle_id": cycle_id,
            "task": task.name,
            "task_description": task.description,
            "repo": task.repo,
            "budget": {
                "max_commits_per_cycle": self._config.budget.max_commits_per_cycle,
                "daily_commit_ceiling": self._config.budget.daily_commit_ceiling,
            },
            # Scout inputs (paths relative to the checkout root).
            "competitors_file": "orchestrate/competitors.yml",
            "papers_file": "research/papers.yaml",
        }

    def _prompt_for(self, role: RoleConfig, context: Dict, schema_hint=None) -> str:
        instructions = load_prompt(role.prompt_file, self._prompts_dir)
        return assemble_prompt(instructions, context, schema_hint=schema_hint)

    def _record(self, entry: LedgerEntry) -> None:
        self._ledger.record(entry)

    # -- phases ------------------------------------------------------------

    def _run_thinkers(
        self, task: TaskConfig, cycle_id: str, deadline: Optional[float]
    ) -> List[RoleOutcome]:
        role_names = task.thinker_roles
        if not role_names:
            return []
        max_workers = max(1, self._config.budget.max_parallel_thinkers)
        # Local SDK bridge is process-global and fights the IDE when launched from
        # worker threads / the editing workspace. Keep local (or serial) thinkers
        # on the calling thread.
        local_runtime = getattr(self._runner._client, "runtime", None) == "local"
        use_pool = (not local_runtime) and max_workers > 1 and len(role_names) > 1

        def _run_one(role_name: str) -> RoleOutcome:
            role = self._role(role_name)
            context = self._base_context(task, cycle_id)
            context["role"] = role_name
            prompt = self._prompt_for(role, context)
            return self._runner.run_role(role, prompt, task.repo, deadline=deadline)

        outcomes: List[RoleOutcome] = []
        if use_pool:
            with ThreadPoolExecutor(
                max_workers=min(max_workers, len(role_names))
            ) as pool:
                for outcome in pool.map(_run_one, role_names):
                    outcomes.append(outcome)
        else:
            for role_name in role_names:
                outcomes.append(_run_one(role_name))

        for outcome in outcomes:
            self._record(
                LedgerEntry(
                    cycle_id=cycle_id,
                    task=task.name,
                    role=outcome.role,
                    status=STATUS_COMPLETED if outcome.ok else STATUS_FAILED,
                    summary=(outcome.result.summary if outcome.result else (outcome.error or "")),
                    agent_id=outcome.agent_id,
                    run_id=outcome.run_id,
                )
            )
        return outcomes

    def _run_judge(
        self,
        task: TaskConfig,
        cycle_id: str,
        proposals: List[Proposal],
        deadline: Optional[float],
    ) -> Optional[RoleOutcome]:
        if not task.judge_role:
            return None
        role = self._role(task.judge_role)
        context = self._base_context(task, cycle_id)
        context["role"] = task.judge_role
        context["proposals"] = [
            {
                "title": p.title,
                "rationale": p.rationale,
                "priority": p.priority,
                "kind": p.kind,
                "source_role": p.source_role,
            }
            for p in proposals
        ]
        schema_hint = {
            "verdict": "execute | hold",
            "summary": "why this choice",
            "data": {
                "execute": True,
                "chosen_title": "exact title of one proposal above",
                "scope": "the bounded change to make",
                "acceptance_criteria": ["checkable condition", "..."],
                "reason": "one-line justification",
            },
        }
        prompt = self._prompt_for(role, context, schema_hint=schema_hint)
        outcome = self._runner.run_role(role, prompt, task.repo, deadline=deadline)
        self._record(
            LedgerEntry(
                cycle_id=cycle_id,
                task=task.name,
                role=outcome.role,
                status=STATUS_COMPLETED if outcome.ok else STATUS_FAILED,
                summary=(outcome.result.summary if outcome.result else (outcome.error or "")),
                agent_id=outcome.agent_id,
                run_id=outcome.run_id,
            )
        )
        return outcome

    def _run_executor(
        self,
        task: TaskConfig,
        cycle_id: str,
        plan: Plan,
        deadline: Optional[float],
    ) -> Optional[RoleOutcome]:
        if not task.executor_role or plan.proposal is None:
            return None
        role = self._role(task.executor_role)

        resumable = find_resumable(self._ledger, task.name)
        resume_agent_id = resumable.agent_id if resumable else None

        context = self._base_context(task, cycle_id)
        context["role"] = task.executor_role
        context["plan"] = {
            "title": plan.proposal.title,
            "rationale": plan.proposal.rationale,
            "scope": plan.scope,
            "acceptance_criteria": plan.acceptance_criteria,
        }
        context["resuming"] = bool(resume_agent_id)
        schema_hint = {
            "verdict": "done | blocked",
            "summary": "what changed and the PR opened",
            "data": {"pr_url": "https://github.com/...", "tests_run": True},
        }
        prompt = self._prompt_for(role, context, schema_hint=schema_hint)

        # Mark in-progress *before* the run so an interruption is resumable.
        self._record(
            LedgerEntry(
                cycle_id=cycle_id,
                task=task.name,
                role=role.name,
                status=STATUS_IN_PROGRESS,
                summary=f"executing: {plan.proposal.title}",
                agent_id=resume_agent_id,
            )
        )

        outcome = self._runner.run_role(
            role,
            prompt,
            task.repo,
            deadline=deadline,
            resume_agent_id=resume_agent_id,
        )

        pr_url = outcome.pr_url or (
            outcome.result.data.get("pr_url") if outcome.result else None
        )
        self._record(
            LedgerEntry(
                cycle_id=cycle_id,
                task=task.name,
                role=role.name,
                status=STATUS_COMPLETED if outcome.ok else STATUS_FAILED,
                summary=(outcome.result.summary if outcome.result else (outcome.error or "")),
                agent_id=outcome.agent_id,
                run_id=outcome.run_id,
                detail={"pr_url": pr_url} if pr_url else {},
            )
        )
        return outcome

    # -- public entrypoint -------------------------------------------------

    def run_cycle(
        self, task_name: str, *, deadline: Optional[float] = None
    ) -> CycleReport:
        task = self._config.get_task(task_name)
        cycle_id = uuid.uuid4().hex[:12]
        report = CycleReport(cycle_id=cycle_id, task=task_name)

        report.thinker_outcomes = self._run_thinkers(task, cycle_id, deadline)
        report.proposals = extract_proposals(report.thinker_outcomes)
        report.judge_outcome = self._run_judge(
            task, cycle_id, report.proposals, deadline
        )
        report.plan = decide_plan(report.judge_outcome, report.proposals)

        if not report.plan.execute:
            report.skipped_reason = report.plan.reason
            return report

        if not self._write_enabled:
            report.skipped_reason = "write disabled (no-write / dry mode)"
            self._record(
                LedgerEntry(
                    cycle_id=cycle_id,
                    task=task_name,
                    role=task.executor_role or "executor",
                    status=STATUS_BLOCKED,
                    summary="plan chosen but code-writing disabled for this run",
                )
            )
            return report

        if self._config.budget.max_code_changing_tasks_per_run < 1:
            report.skipped_reason = "budget forbids code-changing tasks this run"
            return report

        report.executor_outcome = self._run_executor(
            task, cycle_id, report.plan, deadline
        )
        if report.executor_outcome and report.executor_outcome.ok:
            report.pr_url = report.executor_outcome.pr_url or (
                report.executor_outcome.result.data.get("pr_url")
                if report.executor_outcome.result
                else None
            )
        return report
