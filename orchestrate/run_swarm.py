#!/usr/bin/env python3
"""Launch swarm cycle(s) for a task (default: daily corticore maintenance).

Supports two runtimes:

- ``--runtime cloud`` (default for CI): Cursor Cloud agents, optional PR.
- ``--runtime local``: Cursor local agents against a dedicated checkout;
  commits land on main after a green verify gate. Use ``--loop`` to repeat
  cycles inside the operating window up to the daily commit ceiling.

Guards:
- kill switch (`SWARM_ENABLED` must be `true` for any code-writing run),
- daily operating window (unless `--ignore-window`),
- model validation (fail closed if a configured model id isn't available),
- local verify gate (`pytest` + eval) before every push.

Usage:
    python orchestrate/run_swarm.py --dry-run
    python orchestrate/run_swarm.py --runtime local --loop
    python orchestrate/run_swarm.py --runtime cloud --no-write --ignore-window

Requires the `orchestrate` extra for a live run: pip install -e ".[orchestrate]"
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
from swarm.gitops import (  # noqa: E402
    DEFAULT_CHECKOUT,
    author_env,
    count_commits_today,
    discard_local_commits,
    ensure_checkout,
    head_sha,
    infer_bump_from_commits,
    is_release_day,
    last_tag,
    prepare_and_commit_release,
    push_head,
    push_or_reset,
    run_verify_gate,
)
from swarm.ledger import FileLedger, GitHubLedger, InMemoryLedger, Ledger  # noqa: E402
from swarm.models import list_available_model_ids, validate_models  # noqa: E402
from swarm.orchestrator import Orchestrator  # noqa: E402
from swarm.prompts import assemble_prompt, load_prompt  # noqa: E402
from swarm.runner import SwarmRunner  # noqa: E402
from swarm.window import OperatingWindow  # noqa: E402

DEFAULT_CONFIG = ORCHESTRATE_DIR / "swarm.yml"
DEFAULT_PROMPTS_DIR = ORCHESTRATE_DIR / "prompts"
DEFAULT_TASK = "corticore-maintenance"
DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "corticore-swarm"
DEFAULT_STAMP_PATH = DEFAULT_STATE_DIR / "last_run_day"

# Deadline used for on-demand smoke tests that bypass the operating window
# (--ignore-window). Keeps a manual run from hanging past a reasonable cap
# when there is no window-close time to derive a deadline from.
IGNORE_WINDOW_DEADLINE_SECONDS = 3600
# Shorter cap for --catch-up (laptop woke after the morning window).
CATCH_UP_DEADLINE_SECONDS = 5400  # 90 minutes


def kill_switch_enabled(env: dict) -> bool:
    """Code-writing runs require SWARM_ENABLED=true (any case)."""
    return str(env.get("SWARM_ENABLED", "")).strip().lower() == "true"


def already_ran_today(stamp_path: Path, today_iso: str) -> bool:
    """True if the stamp file records today's date (local calendar day)."""
    try:
        return stamp_path.read_text().strip() == today_iso
    except OSError:
        return False


def mark_ran_today(stamp_path: Path, today_iso: str) -> None:
    """Record that a local loop started today (idempotent)."""
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(today_iso + "\n")


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
    ledger_path = Path(
        env.get("SWARM_LEDGER_PATH", str(ORCHESTRATE_DIR / ".swarm_ledger.jsonl"))
    )
    return FileLedger(ledger_path)


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
            "budget": {
                "max_commits_per_cycle": config.budget.max_commits_per_cycle,
                "daily_commit_ceiling": config.budget.daily_commit_ceiling,
            },
        }
        prompt = assemble_prompt(instructions, context)
        print("\n" + "=" * 72)
        print(f"ROLE: {role_name}  MODEL: {role.model}  CAN_WRITE: {role.can_write}")
        print("=" * 72)
        print(prompt)
    print("\n[dry-run] no agents launched, no API key used.")
    return 0


def _print_report(report) -> None:
    print(f"[swarm] cycle {report.cycle_id} task={report.task}")
    print(
        f"[swarm] thinkers: {len(report.thinker_outcomes)} "
        f"({sum(1 for o in report.thinker_outcomes if o.ok)} ok)"
    )
    print(f"[swarm] proposals: {len(report.proposals)}")
    if report.plan is not None:
        print(
            f"[swarm] plan.execute={report.plan.execute} "
            f"reason={report.plan.reason!r}"
        )
    if report.skipped_reason:
        print(f"[swarm] skipped execution: {report.skipped_reason}")
    if report.pr_url:
        print(f"[swarm] PR opened: {report.pr_url}")


def _resolve_deadline(
    window: OperatingWindow,
    ignore_window: bool,
    config,
    *,
    catch_up: bool = False,
    stamp_path: Path = DEFAULT_STAMP_PATH,
) -> Optional[float]:
    """Return a monotonic deadline, or None if outside the window and not ignored.

    `--catch-up` allows one bounded run outside the window when today's stamp
    is missing (laptop was off during 04:00–09:00). Once stamped, later
    catch-up attempts that day are skipped.
    """
    now_local = window.now_local()
    if window.is_open(now_local):
        return time.monotonic() + window.seconds_until_close(now_local)
    if ignore_window:
        print(
            f"[swarm] outside operating window "
            f"({config.window.start}-{config.window.end} {config.window.timezone}), "
            "but --ignore-window set: running an on-demand cycle."
        )
        return time.monotonic() + IGNORE_WINDOW_DEADLINE_SECONDS
    if catch_up:
        today = now_local.date().isoformat()
        if already_ran_today(stamp_path, today):
            print(
                f"[swarm] outside operating window and already ran today "
                f"({today}); catch-up not needed."
            )
            return None
        print(
            f"[swarm] outside operating window "
            f"({config.window.start}-{config.window.end} {config.window.timezone}), "
            f"but --catch-up and no run yet today ({today}): "
            f"starting a bounded catch-up ({CATCH_UP_DEADLINE_SECONDS // 60}m)."
        )
        return time.monotonic() + CATCH_UP_DEADLINE_SECONDS
    print(
        f"[swarm] outside operating window "
        f"({config.window.start}-{config.window.end} {config.window.timezone}); "
        "not starting new work."
    )
    return None


def _maybe_cut_release(config, checkout: Path, window: OperatingWindow) -> int:
    """On the configured release weekday, bump version + CHANGELOG and push."""
    now_local = window.now_local()
    if not is_release_day(config.release.weekday, now_local):
        print(
            f"[swarm] not release day "
            f"(today={now_local.strftime('%A')}, configured={config.release.weekday})."
        )
        return 0

    print(f"[swarm] release day ({config.release.weekday}): preparing version bump.")
    ensure_checkout(checkout)
    tag = last_tag(checkout)
    bump = infer_bump_from_commits(checkout, since_tag=tag)
    env_ident = author_env()
    new_ver = prepare_and_commit_release(
        checkout, bump=bump, author=env_ident
    )
    if new_ver is None:
        print("[swarm] nothing to release (empty Unreleased or no changes).")
        return 0

    verify = run_verify_gate(checkout)
    if not verify.ok:
        print(
            f"[swarm] release verify failed; discarding. "
            f"pytest_ok={verify.pytest_ok} eval_ok={verify.eval_ok}",
            file=sys.stderr,
        )
        discard_local_commits(checkout)
        return 2

    push_head(checkout)
    print(
        f"[swarm] released {new_ver} on main "
        f"(triggers .github/workflows/release.yml when RELEASE_ENABLED=true)."
    )
    return 0


def _run_local_cycle(
    orchestrator: Orchestrator,
    task: str,
    deadline: float,
    checkout: Path,
) -> int:
    """One local cycle: agents edit checkout, then verify+push or reset."""
    ensure_checkout(checkout)
    baseline = head_sha(checkout)
    report = orchestrator.run_cycle(task, deadline=deadline)
    _print_report(report)

    if report.executor_outcome is None:
        # Thinking-only or skipped - nothing to push.
        return 0

    if not report.executor_outcome.ok:
        print("[swarm] executor run failed - discarding local changes.", file=sys.stderr)
        discard_local_commits(checkout)
        return 2

    verify = run_verify_gate(checkout)
    if not verify.ok:
        print(
            f"[swarm] verify gate failed; resetting to origin/main. "
            f"pytest_ok={verify.pytest_ok} eval_ok={verify.eval_ok}",
            file=sys.stderr,
        )
        discard_local_commits(checkout)
        return 2

    result = push_or_reset(checkout, baseline_sha=baseline)
    if result.pushed:
        print(f"[swarm] pushed {result.commits_pushed} commit(s) to origin/main.")
    else:
        print(f"[swarm] nothing to push ({result.reason}).")
    return 0


def _run_local_loop(
    config,
    orchestrator: Orchestrator,
    window: OperatingWindow,
    args,
    commit_ceiling: int,
    *,
    catch_up_active: bool = False,
) -> int:
    """Repeat local cycles while the window is open and under the commit ceiling."""
    checkout = Path(args.checkout).expanduser()
    total_pushed = 0
    cycles = 0
    exit_code = 0
    stamp_path = Path(
        getattr(args, "stamp_path", None) or DEFAULT_STAMP_PATH
    ).expanduser()
    mark_ran_today(stamp_path, window.now_local().date().isoformat())
    catch_up_deadline = (
        time.monotonic() + CATCH_UP_DEADLINE_SECONDS if catch_up_active else None
    )

    while True:
        now_local = window.now_local()
        if (
            not window.is_open(now_local)
            and not args.ignore_window
            and not catch_up_active
        ):
            print("[swarm] window closed; stopping loop.")
            break
        if catch_up_deadline is not None and time.monotonic() >= catch_up_deadline:
            print("[swarm] catch-up time budget exhausted; stopping.")
            break

        commits_before = count_commits_today(
            checkout if checkout.exists() else ensure_checkout(checkout)
        )
        if commits_before >= commit_ceiling:
            print(
                f"[swarm] daily commit ceiling reached "
                f"({commits_before} >= {commit_ceiling}); stopping loop."
            )
            break

        if window.is_open(now_local):
            remaining = window.seconds_until_close(now_local)
        elif catch_up_deadline is not None:
            remaining = max(0.0, catch_up_deadline - time.monotonic())
        else:
            remaining = float(IGNORE_WINDOW_DEADLINE_SECONDS)
        if remaining <= 60 and not args.ignore_window and not catch_up_active:
            print("[swarm] less than 60s left in window; stopping loop.")
            break
        if remaining <= 30:
            print("[swarm] less than 30s left in catch-up/window budget; stopping.")
            break

        deadline = time.monotonic() + remaining
        print(
            f"[swarm] starting local cycle #{cycles + 1} "
            f"(commits_today={commits_before}, ceiling={commit_ceiling})."
        )
        code = _run_local_cycle(orchestrator, args.task, deadline, checkout)
        cycles += 1
        if code != 0:
            exit_code = code
            # Soft-fail: continue the loop unless the window is about to close.
            print(f"[swarm] cycle exited {code}; continuing if window allows.")

        # Refresh count after possible push.
        if checkout.exists():
            commits_after = count_commits_today(checkout)
            total_pushed += max(0, commits_after - commits_before)

        if not args.loop:
            break
        if args.ignore_window and cycles >= 1:
            # On-demand ignore-window: one cycle unless --loop is combined with
            # an open window. If ignore-window + loop, allow multiple but cap
            # at ceiling; still break after a generous single-shot when window closed.
            if not window.is_open(window.now_local()):
                # Allow multiple only while under ceiling; keep going until ceiling
                # or max_cycles safety.
                pass

        # Safety: absolute cycle cap to prevent runaway if something is wrong.
        if cycles >= commit_ceiling:
            print("[swarm] cycle safety cap reached; stopping.")
            break

    print(f"[swarm] loop done: cycles={cycles} approx_new_commits={total_pushed}")

    # Weekly release step (local only).
    if not args.skip_release:
        release_code = _maybe_cut_release(config, checkout, window)
        if release_code != 0:
            return release_code
    return exit_code


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
    parser.add_argument(
        "--ignore-window",
        action="store_true",
        help="Bypass the daily operating-window check (manual smoke tests only).",
    )
    parser.add_argument(
        "--runtime",
        choices=("cloud", "local"),
        default="cloud",
        help="Agent runtime: cloud (Cursor VM) or local (laptop checkout).",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="(local) Repeat cycles until the window closes or the commit ceiling is hit.",
    )
    parser.add_argument(
        "--checkout",
        type=Path,
        default=DEFAULT_CHECKOUT,
        help="(local) Dedicated clone path (never your editing workspace).",
    )
    parser.add_argument(
        "--commit-ceiling",
        type=int,
        default=None,
        help="(local) Override budget.daily_commit_ceiling for this run.",
    )
    parser.add_argument(
        "--skip-release",
        action="store_true",
        help="(local) Do not attempt the Friday version bump at the end of the loop.",
    )
    parser.add_argument(
        "--catch-up",
        action="store_true",
        help=(
            "(local) If outside the operating window and no run stamped today, "
            "still run a bounded loop (for systemd Persistent= wakeups)."
        ),
    )
    parser.add_argument(
        "--stamp-path",
        type=Path,
        default=DEFAULT_STAMP_PATH,
        help="(local) Path of the last-run-day stamp file.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)

    if args.dry_run:
        return _dry_run(config, args.prompts_dir, args.task)

    api_key = env.get("CURSOR_API_KEY")
    if not api_key:
        print(
            "CURSOR_API_KEY is not set. Set it in the environment "
            "(or the systemd unit EnvironmentFile) or use --dry-run.",
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

    window = OperatingWindow(
        timezone=config.window.timezone,
        start=config.window.start,
        end=config.window.end,
    )

    from swarm.cursor_client import build_client

    if args.runtime == "local":
        checkout = Path(args.checkout).expanduser()
        ensure_checkout(checkout)
        client = build_client("local", api_key, cwd=checkout)
    else:
        client = build_client("cloud", api_key)

    runner = SwarmRunner(client)
    ledger = _build_ledger(args, env)
    orchestrator = Orchestrator(
        config, runner, ledger, args.prompts_dir, write_enabled=write_enabled
    )

    commit_ceiling = (
        args.commit_ceiling
        if args.commit_ceiling is not None
        else config.budget.daily_commit_ceiling
    )

    if args.runtime == "local":
        # Local always goes through verify+push; --loop repeats cycles.
        deadline = _resolve_deadline(
            window,
            args.ignore_window,
            config,
            catch_up=args.catch_up,
            stamp_path=Path(args.stamp_path).expanduser(),
        )
        catch_up_active = (
            bool(args.catch_up)
            and not window.is_open(window.now_local())
            and not args.ignore_window
            and deadline is not None
        )
        if deadline is None:
            _write_github_output(env, ran="false", reason="outside_window")
            # Still allow release-day bump outside the window if requested.
            if not args.skip_release:
                return _maybe_cut_release(
                    config, Path(args.checkout).expanduser(), window
                )
            return 0

        if args.loop:
            code = _run_local_loop(
                config,
                orchestrator,
                window,
                args,
                commit_ceiling,
                catch_up_active=catch_up_active,
            )
        else:
            mark_ran_today(
                Path(args.stamp_path).expanduser(),
                window.now_local().date().isoformat(),
            )
            code = _run_local_cycle(
                orchestrator, args.task, deadline, Path(args.checkout).expanduser()
            )
            if not args.skip_release:
                release_code = _maybe_cut_release(
                    config, Path(args.checkout).expanduser(), window
                )
                if release_code != 0:
                    return release_code
        _write_github_output(env, ran="true", executed=str(write_enabled).lower())
        return code

    # Cloud single-cycle path (existing behaviour).
    deadline = _resolve_deadline(window, args.ignore_window, config)
    if deadline is None:
        _write_github_output(env, ran="false", reason="outside_window")
        return 0

    report = orchestrator.run_cycle(args.task, deadline=deadline)
    _print_report(report)

    _write_github_output(
        env,
        ran="true",
        executed=str(report.executed()).lower(),
        pr_url=report.pr_url or "",
    )

    if report.executor_outcome is not None and not report.executor_outcome.ok:
        print("[swarm] executor run failed - see ledger/dashboard.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
