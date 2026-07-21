"""Deterministic git helpers for the local swarm loop.

All work happens in a *dedicated* checkout (never the user's editing
workspace). After each executor cycle the orchestrator:

1. counts new commits since the pre-cycle HEAD,
2. runs the local verify gate (`pytest` + eval baseline),
3. pushes if green, otherwise `git reset --hard` to discard.

Author/committer identity is pinned via `GIT_AUTHOR_*` / `GIT_COMMITTER_*`
env for any commits *we* create (e.g. the weekly release bump). Executor
commits inherit whatever identity the local agent used; we do not rewrite
them. Global git config is never modified.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Sequence

DEFAULT_CHECKOUT = Path.home() / ".local" / "share" / "corticore-swarm" / "checkout"
DEFAULT_REMOTE_URL = "git@github.com:mastroke/corticore.git"
DEFAULT_BRANCH = "main"


class GitOpsError(RuntimeError):
    """Raised when a required git/verify step fails."""


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    pytest_ok: bool
    eval_ok: bool
    stdout: str
    stderr: str


@dataclass(frozen=True)
class PushResult:
    pushed: bool
    commits_pushed: int
    reason: str


def _run(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    runner=subprocess.run,
) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = runner(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise GitOpsError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def author_env(
    name: Optional[str] = None,
    email: Optional[str] = None,
    *,
    runner=subprocess.run,
) -> Dict[str, str]:
    """Build GIT_AUTHOR_*/GIT_COMMITTER_* from args or the ambient git config.

    Never writes to git config; only reads `user.name` / `user.email`.
    """
    if not name:
        name = (
            _run(["git", "config", "--get", "user.name"], check=False, runner=runner)
            .stdout.strip()
            or "Masoob Alam"
        )
    if not email:
        email = (
            _run(["git", "config", "--get", "user.email"], check=False, runner=runner)
            .stdout.strip()
            or "masoob0085@gmail.com"
        )
    return {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
    }


def ensure_checkout(
    checkout: Path,
    *,
    remote_url: str = DEFAULT_REMOTE_URL,
    branch: str = DEFAULT_BRANCH,
    author_name: Optional[str] = None,
    author_email: Optional[str] = None,
    runner=subprocess.run,
) -> Path:
    """Clone (if needed) and hard-reset the dedicated checkout to origin/branch.

    Sets *local* (repo-only) `user.name` / `user.email` from the ambient git
    config (or explicit overrides) so executor commits carry the right identity
    without touching the user's global git config.
    """
    checkout = Path(checkout)
    checkout.parent.mkdir(parents=True, exist_ok=True)
    if not (checkout / ".git").exists():
        _run(
            ["git", "clone", "--branch", branch, remote_url, str(checkout)],
            runner=runner,
        )
    else:
        _run(["git", "fetch", "origin", branch], cwd=checkout, runner=runner)
        _run(["git", "checkout", branch], cwd=checkout, runner=runner)
        _run(
            ["git", "reset", "--hard", f"origin/{branch}"],
            cwd=checkout,
            runner=runner,
        )
        _run(["git", "clean", "-fd"], cwd=checkout, runner=runner)

    ident = author_env(author_name, author_email, runner=runner)
    _run(
        ["git", "config", "user.name", ident["GIT_AUTHOR_NAME"]],
        cwd=checkout,
        runner=runner,
    )
    _run(
        ["git", "config", "user.email", ident["GIT_AUTHOR_EMAIL"]],
        cwd=checkout,
        runner=runner,
    )
    return checkout


def head_sha(checkout: Path, *, runner=subprocess.run) -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=checkout, runner=runner)
    return result.stdout.strip()


def count_commits_since(
    checkout: Path, since_sha: str, *, runner=subprocess.run
) -> int:
    """Number of commits reachable from HEAD but not from `since_sha`."""
    if not since_sha:
        return 0
    result = _run(
        ["git", "rev-list", "--count", f"{since_sha}..HEAD"],
        cwd=checkout,
        runner=runner,
    )
    return int((result.stdout or "0").strip() or "0")


def count_commits_today(
    checkout: Path,
    *,
    now_local: Optional[datetime] = None,
    author_email: Optional[str] = None,
    runner=subprocess.run,
) -> int:
    """Commits on HEAD's branch authored since local midnight today."""
    now_local = now_local or datetime.now().astimezone()
    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    since = midnight.isoformat()
    cmd = ["git", "rev-list", "--count", "HEAD", f"--since={since}"]
    if author_email:
        cmd.append(f"--author={author_email}")
    result = _run(cmd, cwd=checkout, runner=runner)
    return int((result.stdout or "0").strip() or "0")


def run_verify_gate(
    checkout: Path,
    *,
    python: Optional[str] = None,
    runner=subprocess.run,
) -> VerifyResult:
    """Run pytest + eval/check_baseline.py in the checkout. Pure of git side effects."""
    py = python or sys.executable
    # Best-effort editable install so imports resolve; ignore failure if already set.
    _run(
        [py, "-m", "pip", "install", "-e", ".[dev]", "-q"],
        cwd=checkout,
        check=False,
        runner=runner,
    )
    pytest_result = _run(
        [py, "-m", "pytest", "-q"], cwd=checkout, check=False, runner=runner
    )
    eval_result = _run(
        [py, "eval/check_baseline.py"], cwd=checkout, check=False, runner=runner
    )
    stdout = (pytest_result.stdout or "") + "\n" + (eval_result.stdout or "")
    stderr = (pytest_result.stderr or "") + "\n" + (eval_result.stderr or "")
    return VerifyResult(
        ok=pytest_result.returncode == 0 and eval_result.returncode == 0,
        pytest_ok=pytest_result.returncode == 0,
        eval_ok=eval_result.returncode == 0,
        stdout=stdout,
        stderr=stderr,
    )


def push_or_reset(
    checkout: Path,
    *,
    baseline_sha: str,
    branch: str = DEFAULT_BRANCH,
    runner=subprocess.run,
) -> PushResult:
    """If HEAD is ahead of baseline and the verify gate is green, push; else reset.

    Returns a `PushResult` describing what happened. Does not call verify itself -
    the caller must verify first and only call this when green (or call
    `discard_local_commits` on red).
    """
    new_commits = count_commits_since(checkout, baseline_sha, runner=runner)
    if new_commits == 0:
        return PushResult(pushed=False, commits_pushed=0, reason="no_new_commits")
    _run(["git", "push", "origin", f"HEAD:{branch}"], cwd=checkout, runner=runner)
    return PushResult(
        pushed=True, commits_pushed=new_commits, reason="pushed"
    )


def discard_local_commits(
    checkout: Path,
    *,
    branch: str = DEFAULT_BRANCH,
    runner=subprocess.run,
) -> None:
    """Hard-reset the checkout to origin/branch and clean untracked files."""
    _run(["git", "fetch", "origin", branch], cwd=checkout, runner=runner)
    _run(
        ["git", "reset", "--hard", f"origin/{branch}"],
        cwd=checkout,
        runner=runner,
    )
    _run(["git", "clean", "-fd"], cwd=checkout, runner=runner)


def push_head(
    checkout: Path,
    *,
    branch: str = DEFAULT_BRANCH,
    runner=subprocess.run,
) -> None:
    """Push the current HEAD to origin/branch."""
    _run(["git", "push", "origin", f"HEAD:{branch}"], cwd=checkout, runner=runner)


def is_release_day(weekday_name: str, now_local: datetime) -> bool:
    """True when `now_local`'s weekday matches the configured release day name."""
    return now_local.strftime("%A") == weekday_name


def prepare_and_commit_release(
    checkout: Path,
    *,
    bump: str = "patch",
    date: Optional[str] = None,
    author: Optional[Dict[str, str]] = None,
    runner=subprocess.run,
) -> Optional[str]:
    """Bump version + roll CHANGELOG and commit on the current branch.

    Uses the pure helpers from `prepare_release`. Returns the new version, or
    None if the Unreleased section is empty (nothing to release). Does not push.
    """
    # Import here so gitops stays importable without the prepare_release path
    # being on sys.path in every context; orchestrate/ is on path for run_swarm.
    orchestrate_dir = Path(__file__).resolve().parent.parent
    if str(orchestrate_dir) not in sys.path:
        sys.path.insert(0, str(orchestrate_dir))
    import prepare_release as prep  # noqa: WPS433

    pyproject = checkout / "pyproject.toml"
    changelog = checkout / "CHANGELOG.md"
    current = prep.read_current_version(pyproject.read_text())
    from swarm.gates import next_version  # local import after path setup

    new_ver = next_version(current, bump)
    release_date = date or datetime.now().date().isoformat()
    try:
        new_changelog = prep.roll_changelog(
            changelog.read_text(), new_ver, release_date
        )
    except ValueError as exc:
        # Empty Unreleased - nothing to cut.
        if "no entries" in str(exc).lower() or "unreleased" in str(exc).lower():
            return None
        raise

    pyproject.write_text(prep.set_pyproject_version(pyproject.read_text(), new_ver))
    changelog.write_text(new_changelog)

    env = author or author_env(runner=runner)
    _run(["git", "add", "pyproject.toml", "CHANGELOG.md"], cwd=checkout, runner=runner)
    # Skip if nothing staged (defensive).
    status = _run(
        ["git", "status", "--porcelain"], cwd=checkout, check=False, runner=runner
    )
    if not (status.stdout or "").strip():
        return None
    _run(
        ["git", "commit", "-m", f"Release {new_ver}"],
        cwd=checkout,
        env=env,
        runner=runner,
    )
    return new_ver


def infer_bump_from_commits(
    checkout: Path,
    *,
    since_tag: Optional[str],
    runner=subprocess.run,
) -> str:
    """Heuristic bump from conventional commit subjects since `since_tag`.

    Defaults to `patch` when nothing stronger is found. Looking for `BREAKING`
    / `!:` -> major, `feat` -> minor.
    """
    range_spec = f"{since_tag}..HEAD" if since_tag else "HEAD"
    result = _run(
        ["git", "log", "--format=%s", range_spec],
        cwd=checkout,
        check=False,
        runner=runner,
    )
    subjects = (result.stdout or "").splitlines()
    bump = "patch"
    for subject in subjects:
        lower = subject.lower()
        if "breaking change" in lower or lower.startswith("break") or "!:" in subject:
            return "major"
        if lower.startswith("feat") or lower.startswith("feature"):
            bump = "minor"
    return bump


def last_tag(checkout: Path, *, runner=subprocess.run) -> Optional[str]:
    result = _run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=checkout,
        check=False,
        runner=runner,
    )
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None
