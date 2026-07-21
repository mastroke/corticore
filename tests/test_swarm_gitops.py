"""Tests for local-swarm gitops helpers (real temp git repos, no network)."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.gitops import (  # noqa: E402
    author_env,
    count_commits_since,
    count_commits_today,
    discard_local_commits,
    head_sha,
    infer_bump_from_commits,
    is_release_day,
    prepare_and_commit_release,
    push_or_reset,
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        text=True,
        capture_output=True,
    )
    return (result.stdout or "").strip()


def _init_repo(tmp_path: Path) -> Path:
    """Create a bare origin + a working clone that looks like main."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(
        ["git", "clone", str(origin), str(work)], check=True, capture_output=True
    )
    _git(work, "config", "user.name", "Test User")
    _git(work, "config", "user.email", "test@example.com")
    (work / "README").write_text("hi\n")
    (work / "pyproject.toml").write_text('version = "0.1.0"\n')
    (work / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Fixed\n\n- something\n"
    )
    _git(work, "add", ".")
    _git(work, "commit", "-m", "init")
    # Rename default branch to main if needed.
    branch = _git(work, "branch", "--show-current") or "master"
    if branch != "main":
        _git(work, "branch", "-M", "main")
    _git(work, "push", "-u", "origin", "main")
    return work


def test_head_sha_and_count_commits_since(tmp_path):
    work = _init_repo(tmp_path)
    base = head_sha(work)
    assert count_commits_since(work, base) == 0
    (work / "README").write_text("hi2\n")
    _git(work, "add", "README")
    _git(work, "commit", "-m", "feat: bump")
    assert count_commits_since(work, base) == 1


def test_count_commits_today(tmp_path):
    work = _init_repo(tmp_path)
    # The init commit is today in the temp repo.
    n = count_commits_today(work, now_local=datetime.now().astimezone())
    assert n >= 1


def test_author_env_reads_git_config(tmp_path):
    work = _init_repo(tmp_path)
    # Run from the work tree so config is local; author_env uses global/ambient
    # git config by default. Pass explicit values instead.
    env = author_env(name="Masoob Alam", email="masoob0085@gmail.com")
    assert env["GIT_AUTHOR_NAME"] == "Masoob Alam"
    assert env["GIT_AUTHOR_EMAIL"] == "masoob0085@gmail.com"
    assert env["GIT_COMMITTER_NAME"] == "Masoob Alam"
    del work


def test_is_release_day():
    friday = datetime(2026, 7, 17, 10, 0, 0)  # a Friday
    assert is_release_day("Friday", friday) is True
    assert is_release_day("Monday", friday) is False


def test_infer_bump_from_commits(tmp_path):
    work = _init_repo(tmp_path)
    (work / "a").write_text("1\n")
    _git(work, "add", "a")
    _git(work, "commit", "-m", "feat: add a")
    assert infer_bump_from_commits(work, since_tag=None) == "minor"

    (work / "b").write_text("2\n")
    _git(work, "add", "b")
    _git(work, "commit", "-m", "fix: typo")
    # Still minor because feat is in history.
    assert infer_bump_from_commits(work, since_tag=None) == "minor"


def test_prepare_and_commit_release(tmp_path):
    work = _init_repo(tmp_path)
    new_ver = prepare_and_commit_release(
        work,
        bump="patch",
        date="2026-07-21",
        author=author_env(name="Masoob Alam", email="masoob0085@gmail.com"),
    )
    assert new_ver == "0.1.1"
    py = (work / "pyproject.toml").read_text()
    assert 'version = "0.1.1"' in py
    cl = (work / "CHANGELOG.md").read_text()
    assert "## [0.1.1] - 2026-07-21" in cl
    assert "Release 0.1.1" in _git(work, "log", "-1", "--format=%s")


def test_push_or_reset_pushes_when_ahead(tmp_path):
    work = _init_repo(tmp_path)
    base = head_sha(work)
    (work / "README").write_text("pushed\n")
    _git(work, "add", "README")
    _git(work, "commit", "-m", "chore: push me")
    result = push_or_reset(work, baseline_sha=base, branch="main")
    assert result.pushed is True
    assert result.commits_pushed == 1


def test_discard_local_commits(tmp_path):
    work = _init_repo(tmp_path)
    (work / "README").write_text("gone\n")
    _git(work, "add", "README")
    _git(work, "commit", "-m", "chore: discard me")
    discard_local_commits(work, branch="main")
    assert (work / "README").read_text() == "hi\n"
