"""Tests for the eval regression-gate baseline parser (pure)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))

from check_baseline import parse_baseline_score  # noqa: E402


def test_parses_highest_percentage():
    text = "| 2026-07-06 | synthetic-v0 | recall@3 = 4/5 | 80% | notes |\n| 2026-07-10 | x | y | 100% | z |"
    assert parse_baseline_score(text) == 1.0


def test_single_score():
    assert parse_baseline_score("Score 80% baseline") == 0.8


def test_no_percentage_returns_none():
    assert parse_baseline_score("no numbers here") is None


def test_ignores_out_of_range_values():
    # 200% isn't a valid recall score; the 80% should win.
    assert parse_baseline_score("weird 200% but real 80%") == 0.8


def test_real_baseline_file_parses():
    baseline = REPO_ROOT / "eval" / "BASELINE.md"
    score = parse_baseline_score(baseline.read_text())
    assert score is not None and 0.0 <= score <= 1.0
