#!/usr/bin/env python3
"""Deterministically prepare a release-candidate PR (no LLM in the loop).

Versioning is far too consequential to leave to a model's judgement, so the
bump is computed as a boring function of the change labels merged since the
last release tag (see `swarm.gates`). This script:

1. collects `breaking`/`feature`/`fix` labels from PRs merged since the last
   tag (via `gh`),
2. computes the next semantic version,
3. bumps `pyproject.toml` and rolls the CHANGELOG `Unreleased` section under a
   dated version heading,
4. opens one `Release <version>` PR and enables auto-merge.

The publish itself (`.github/workflows/release.yml`) happens only after CI and
the independent verifier pass and every release gate clears. The pure text
transforms here are unit-tested; the `gh`/`git` calls run only in CI.

Usage:
    python orchestrate/prepare_release.py [--dry-run] [--repo owner/name]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

ORCHESTRATE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ORCHESTRATE_DIR.parent
sys.path.insert(0, str(ORCHESTRATE_DIR))

from swarm.gates import bump_type, next_version  # noqa: E402

PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

_VERSION_RE = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.MULTILINE)


def read_current_version(pyproject_text: str) -> str:
    match = _VERSION_RE.search(pyproject_text)
    if not match:
        raise ValueError("could not find version in pyproject.toml")
    return match.group(2)


def set_pyproject_version(pyproject_text: str, new_version: str) -> str:
    """Replace the first `version = "..."` with `new_version` (pure)."""
    new_text, count = _VERSION_RE.subn(
        lambda m: f'{m.group(1)}"{new_version}"', pyproject_text, count=1
    )
    if count != 1:
        raise ValueError("failed to replace exactly one version line")
    return new_text


def roll_changelog(changelog_text: str, version: str, date: str) -> str:
    """Move the `Unreleased` entries under a dated `[version]` heading (pure).

    Raises if there is no `Unreleased` section or it has no entries - you
    should never cut a release with an empty changelog.
    """
    marker = "## [Unreleased]"
    idx = changelog_text.find(marker)
    if idx == -1:
        raise ValueError("CHANGELOG has no '## [Unreleased]' section")

    body_start = idx + len(marker)
    next_heading = changelog_text.find("\n## [", body_start)
    if next_heading == -1:
        unreleased_body = changelog_text[body_start:]
        tail = ""
    else:
        unreleased_body = changelog_text[body_start:next_heading]
        tail = changelog_text[next_heading + 1 :]  # drop the leading newline

    stripped_body = unreleased_body.strip("\n")
    if not stripped_body.strip():
        raise ValueError("CHANGELOG '[Unreleased]' section has no entries to release")

    head = changelog_text[:idx]
    new_block = (
        f"{marker}\n\n"
        f"## [{version}] - {date}\n\n"
        f"{stripped_body}\n"
    )
    rebuilt = f"{head}{new_block}"
    if tail:
        rebuilt += f"\n{tail}"
    return rebuilt


# --- side-effecting helpers (CI only) ---------------------------------------


def _run(cmd: List[str], runner=subprocess.run, **kw):
    return runner(cmd, check=True, text=True, capture_output=True, **kw)


def _last_tag(runner=subprocess.run) -> Optional[str]:
    try:
        result = runner(
            ["git", "describe", "--tags", "--abbrev=0"],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return None
    return (result.stdout or "").strip() or None


def collect_merged_labels(repo: str, since_tag: Optional[str], runner=subprocess.run) -> List[str]:
    """Labels on PRs merged since `since_tag` (best-effort via `gh`)."""
    args = [
        "gh",
        "pr",
        "list",
        "--repo",
        repo,
        "--state",
        "merged",
        "--limit",
        "200",
        "--json",
        "labels,mergedAt",
    ]
    result = runner(args, check=True, text=True, capture_output=True)
    import json

    prs = json.loads(result.stdout or "[]")

    since_iso = None
    if since_tag:
        try:
            tag_date = runner(
                ["git", "log", "-1", "--format=%cI", since_tag],
                check=True,
                text=True,
                capture_output=True,
            )
            since_iso = (tag_date.stdout or "").strip()
        except subprocess.CalledProcessError:
            since_iso = None

    labels: List[str] = []
    for pr in prs:
        if since_iso and pr.get("mergedAt", "") <= since_iso:
            continue
        for label in pr.get("labels", []):
            name = label.get("name") if isinstance(label, dict) else label
            if name:
                labels.append(str(name))
    return labels


def main(argv: Optional[list] = None, runner=subprocess.run) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="mastroke/corticore")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    pyproject_text = PYPROJECT.read_text()
    current = read_current_version(pyproject_text)

    since_tag = _last_tag(runner)
    labels = collect_merged_labels(args.repo, since_tag, runner=runner)
    bump = bump_type(labels)
    if bump is None:
        print("[release-prep] no release-relevant labelled changes; nothing to release.")
        return 0

    new_ver = next_version(current, bump)
    date = _dt.date.today().isoformat()
    print(f"[release-prep] {current} -> {new_ver} ({bump}) from labels: {sorted(set(labels))}")

    new_pyproject = set_pyproject_version(pyproject_text, new_ver)
    new_changelog = roll_changelog(CHANGELOG.read_text(), new_ver, date)

    if args.dry_run:
        print(f"[dry-run] would set version to {new_ver} and roll the CHANGELOG.")
        return 0

    PYPROJECT.write_text(new_pyproject)
    CHANGELOG.write_text(new_changelog)

    branch = f"release/v{new_ver}"
    _run(["git", "checkout", "-b", branch], runner=runner)
    _run(["git", "add", "pyproject.toml", "CHANGELOG.md"], runner=runner)
    _run(["git", "commit", "-m", f"Release {new_ver}"], runner=runner)
    _run(["git", "push", "-u", "origin", branch], runner=runner)
    _run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            args.repo,
            "--title",
            f"Release {new_ver}",
            "--label",
            "release",
            "--body",
            f"Automated release candidate: {current} -> {new_ver} ({bump}).\n\n"
            "Merges only after CI and the independent verifier pass. The publish "
            "workflow tags, builds, and publishes to PyPI via Trusted Publishing "
            "once every release gate clears.",
        ],
        runner=runner,
    )
    _run(["gh", "pr", "merge", "--repo", args.repo, "--auto", "--squash", branch], runner=runner)
    print(f"[release-prep] opened release PR for {new_ver} with auto-merge enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
