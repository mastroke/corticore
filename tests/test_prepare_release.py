"""Tests for the pure text transforms in prepare_release.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from prepare_release import (  # noqa: E402
    read_current_version,
    roll_changelog,
    set_pyproject_version,
)

_PYPROJECT = """\
[project]
name = "corticore"
version = "0.1.0"
description = "x"
"""

_CHANGELOG = """\
# Changelog

## [Unreleased]

### Added

- A new thing.

## [0.1.0]

- Initial alpha.
"""


def test_read_current_version():
    assert read_current_version(_PYPROJECT) == "0.1.0"


def test_set_pyproject_version_replaces_once():
    out = set_pyproject_version(_PYPROJECT, "0.2.0")
    assert 'version = "0.2.0"' in out
    assert out.count('version = "') == 1


def test_roll_changelog_moves_unreleased():
    out = roll_changelog(_CHANGELOG, "0.2.0", "2026-07-17")
    assert "## [0.2.0] - 2026-07-17" in out
    assert "- A new thing." in out
    # A fresh, empty Unreleased header remains above the new version.
    unreleased_idx = out.index("## [Unreleased]")
    version_idx = out.index("## [0.2.0]")
    assert unreleased_idx < version_idx
    # The prior release is preserved.
    assert "## [0.1.0]" in out


def test_roll_changelog_requires_entries():
    empty = "# Changelog\n\n## [Unreleased]\n\n## [0.1.0]\n\n- old\n"
    with pytest.raises(ValueError, match="no entries"):
        roll_changelog(empty, "0.2.0", "2026-07-17")


def test_roll_changelog_requires_unreleased_section():
    with pytest.raises(ValueError, match="Unreleased"):
        roll_changelog("# Changelog\n\n## [0.1.0]\n", "0.2.0", "2026-07-17")


def test_real_files_transform_cleanly():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text()
    current = read_current_version(pyproject)
    bumped = set_pyproject_version(pyproject, "9.9.9")
    assert '"9.9.9"' in bumped and current != "9.9.9"
    rolled = roll_changelog(changelog, "9.9.9", "2026-07-17")
    assert "## [9.9.9] - 2026-07-17" in rolled
