"""Tests for the SDK repo URL normalizer (pure; no cursor-sdk needed)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.cursor_client import repo_to_url  # noqa: E402


def test_slug_becomes_github_url():
    assert repo_to_url("mastroke/corticore") == "https://github.com/mastroke/corticore"


def test_https_url_passthrough():
    url = "https://github.com/mastroke/corticore"
    assert repo_to_url(url) == url


def test_ssh_url_passthrough():
    url = "git@github.com:mastroke/corticore.git"
    assert repo_to_url(url) == url


def test_strips_whitespace():
    assert repo_to_url("  mastroke/corticore  ") == "https://github.com/mastroke/corticore"
