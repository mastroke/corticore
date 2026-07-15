#!/usr/bin/env python3
"""Launch one swarm cycle for a task (default: the daily maintenance loop).

This is the daily entrypoint the GitHub Actions scheduler calls. It wires the
pure orchestration core (`orchestrate/swarm/`) to the real Cursor SDK and a
GitHub-backed ledger, under three hard guards:

- a kill switch (`SWARM_ENABLED` must be `true` for any code-writing run),
- the daily operating window (no new work started once the window closes),
- model validation (fail closed if a configured model id isn't available).

Usage:
    python orchestrate/run_swarm.py [--task corticore-maintenance]
        [--dry-run] [--no-write] [--config PATH] [--prompts-dir PATH]

`--dry-run` assembles and prints every prompt without launching an agent or
needing an API key. `--no-write` runs thinkers + judge for real but never
runs the code-writing executor. Requires the `orchestrate` extra for a live
run: pip install -e ".[orchestrate]"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Optional

ORCHESTRATE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ORCHESTRATE_DIR))

from swarm.config import load_config  # noqa: E402
from swarm.ledger import FileLedger, GitHubLedger, InMemoryLedger, Ledger  # noqa: E402
from swarm.models import list_available_model_ids, validate_models  # noqa: E402
from swarm.orchestrator import Orchestrator  # noqa: E402
from swarm.prompts import assemble_prompt, load_prompt  # noqa: E402
from swarm.runner import SwarmRunner  # noqa: E402
from swarm.window import OperatingWindow  # noqa: E402

DEFAULT_CONFIG = ORCHESTRATE_DIR / "swarm.yml"
DEFAULT_PROMPTS_DIR = ORCHESTRATE_DIR / "prompts"
DEFAULT_TASK = "corticore-maintenance"


def kill_switch_enabled(env: dict) -> bool:
    """Code-writing runs require SWARM_ENABLED=true (any case)."""
    return str(env.get("SWARM_ENABLED", "")).strip().lower() == "true"


def _write_github_output(env: dict, **pairs) -> None:
    path = env.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a") as f:
        for key, value in pairs.items():
            f.write(f"{key}={value}\n")


def _build_ledger(args, env: dict) -> Ledger:
    if args.dry_run:
        return InMemoryLedger()
    repo = env.get("GITHUB_REPOSITORY")
    issue = env.get("SWARM_LEDGER_ISSUE")
    if repo and issue and issue.isdigit():
        return GitHubLedger(repo=repo, issue_number=int(issue))
    return FileLedger(ORCHESTRATE_DIR / ".swarm_ledger.jsonl")


def _dry_run(config, prompts_dir: Path, task_name: str) -> int:
    """Print every prompt the cycle would send, without launching anything."""
    task = config.get_task(task_name)
    print(f"[dry-run] task: {task.name} ({task.repo})")
    for role_name in task.thinker_roles + [
        r for r in (task.judge_role, task.executor_role, task.verifier_role) if r
    ]:
        role = config.roles[role_name]
        instructions = load_prompt(role.prompt_file, prompts_dir)
        context = {
            "cycle_id": "dry-run",
            "task": task.name,
            "task_description": task.description,
            "repo": task.repo,
            "role": role_name,
        }
        prompt = assemble_prompt(instructions, context)
        print("\n" + "=" * 72)
        print(f"ROLE: {role_name}  MODEL: {role.model}  CAN_WRITE: {role.can_write}")
        print("=" * 72)
        print(prompt)
    print("\n[dry-run] no agents launched, no API key used.")
    return 0


def main(argv: Optional[list] = None, env: Optional[dict] = None) -> int:
    env = env if env is not None else os.environ
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--prompts-dir", type=Path, default=DEFAULT_PROMPTS_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Run thinkers/judge for real but never run the code-writing executor.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)

    if args.dry_run:
        return _dry_run(config, args.prompts_dir, args.task)

    api_key = env.get("CURSOR_API_KEY")
    if not api_key:
        print(
            "CURSOR_API_KEY is not set. Set it (a repository/service-account "
            "secret in CI) or use --dry-run to preview prompts.",
            file=sys.stderr,
        )
        return 1

    # Fail closed on model availability before spending a single run.
    try:
        available = list_available_model_ids(api_key)
        validate_models(config.required_model_ids(), available)
    except Exception as exc:  # noqa: BLE001 - surface any pre-flight failure clearly
        print(f"model pre-flight failed: {exc}", file=sys.stderr)
        return 1

    write_enabled = not args.no_write and kill_switch_enabled(env)
    if args.no_write:
        print("[swarm] --no-write: executor will not run this cycle.")
    elif not kill_switch_enabled(env):
        print("[swarm] SWARM_ENABLED != true: executor disabled (thinking only).")

    # Operating window / deadline.
    window = OperatingWindow(
        timezone=config.window.timezone,
        start=config.window.start,
        end=config.window.end,
    )
    now_local = window.now_local()
    if not window.is_open(now_local):
        print(
            f"[swarm] outside operating window "
            f"({config.window.start}-{config.window.end} {config.window.timezone}); "
            "not starting new work."
        )
        _write_github_output(env, ran="false", reason="outside_window")
        return 0
    deadline = time.monotonic() + window.seconds_until_close(now_local)

    from swarm.cursor_client import CursorCloudClient

    client = CursorCloudClient(api_key=api_key)
    runner = SwarmRunner(client)
    ledger = _build_ledger(args, env)
    orchestrator = Orchestrator(
        config, runner, ledger, args.prompts_dir, write_enabled=write_enabled
    )

    report = orchestrator.run_cycle(args.task, deadline=deadline)

    print(f"[swarm] cycle {report.cycle_id} task={report.task}")
    print(f"[swarm] thinkers: {len(report.thinker_outcomes)} "
          f"({sum(1 for o in report.thinker_outcomes if o.ok)} ok)")
    print(f"[swarm] proposals: {len(report.proposals)}")
    if report.plan is not None:
        print(f"[swarm] plan.execute={report.plan.execute} reason={report.plan.reason!r}")
    if report.skipped_reason:
        print(f"[swarm] skipped execution: {report.skipped_reason}")
    if report.pr_url:
        print(f"[swarm] PR opened: {report.pr_url}")

    _write_github_output(
        env,
        ran="true",
        executed=str(report.executed()).lower(),
        pr_url=report.pr_url or "",
    )

    # A cycle that thought but chose not to (or couldn't) execute is success.
    if report.executor_outcome is not None and not report.executor_outcome.ok:
        print("[swarm] executor run failed - see ledger/dashboard.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
