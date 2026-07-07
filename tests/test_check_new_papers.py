"""Tests for orchestrate/check_new_papers.py.

Pure functions only - no network call and no dependency on pyyaml being
importable at collection time (main()'s network/yaml path is exercised
manually, see the plan's Verification step, not in the unit test suite).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from check_new_papers import filter_new, parse_papers  # noqa: E402

_FIXTURE_README = """\
# Agent-Memory-Paper-List

## Factual Memory

- [2026/01] EverMemOS: A Self-Organizing Memory Operating System for Structured Long-Horizon Reasoning. [[paper](https://www.arxiv.org/abs/2601.02163)]
- [2026/02] A Brand New Paper About Factual Memory. [[paper](https://arxiv.org/abs/2602.99999)]
- [2025/12] Hindsight is 20/20: Building Agent Memory that Retains, Recalls, and Reflects. [[paper](https://arxiv.org/abs/2512.12818)]
- [2026/03] No Arxiv Id Paper. [[paper](https://openreview.net/forum?id=abc123)]

## Working Memory

- [2026/01] EverMemOS: A Self-Organizing Memory Operating System for Structured Long-Horizon Reasoning. [[paper](https://www.arxiv.org/abs/2601.02163)]
- [2026/01] MemRL: Self-Evolving Agents via Runtime Reinforcement Learning on Episodic Memory. [[paper]](https://arxiv.org/abs/2601.03192)
"""


def test_parse_papers_extracts_id_title_date_url():
    papers = parse_papers(_FIXTURE_README)
    ids = {p["id"] for p in papers}

    assert "2601.02163" in ids
    assert "2602.99999" in ids
    assert "2512.12818" in ids
    assert "2601.03192" in ids

    evermemos = next(p for p in papers if p["id"] == "2601.02163")
    assert evermemos["date"] == "2026-01"
    assert evermemos["url"] == "https://www.arxiv.org/abs/2601.02163"
    assert "EverMemOS" in evermemos["title"]
    assert evermemos["title"].endswith("Long-Horizon Reasoning")


def test_parse_papers_dedupes_repeated_ids_across_sections():
    papers = parse_papers(_FIXTURE_README)
    ids = [p["id"] for p in papers]

    assert ids.count("2601.02163") == 1


def test_parse_papers_skips_entries_without_a_resolvable_arxiv_id():
    papers = parse_papers(_FIXTURE_README)
    ids = {p["id"] for p in papers}

    assert not any("openreview" in p["url"] for p in papers)
    assert len(ids) == 4


def test_parse_papers_handles_bracket_variant_without_inner_brackets():
    # "MemRL" uses `[[paper]](url)` instead of `[[paper](url)]` - both must parse.
    papers = parse_papers(_FIXTURE_README)
    memrl = next(p for p in papers if p["id"] == "2601.03192")

    assert memrl["date"] == "2026-01"
    assert "MemRL" in memrl["title"]


def test_filter_new_respects_cutoff_and_known_ids():
    papers = parse_papers(_FIXTURE_README)
    known_ids = {"2601.02163", "2601.03192"}

    new = filter_new(papers, known_ids, cutoff="2026-01")
    new_ids = {p["id"] for p in new}

    assert new_ids == {"2602.99999"}


def test_filter_new_excludes_everything_before_cutoff():
    papers = parse_papers(_FIXTURE_README)

    new = filter_new(papers, known_ids=set(), cutoff="2026-01")
    new_ids = {p["id"] for p in new}

    assert "2512.12818" not in new_ids


def test_real_papers_yaml_jan_2026_papers_all_show_as_already_known():
    """Regression guard: every Jan-2026 paper already tracked in
    research/papers.yaml must never be re-flagged as "new" by a live run.
    """
    yaml = pytest.importorskip("yaml")  # part of the `orchestrate` extra

    papers_yaml_path = REPO_ROOT / "research" / "papers.yaml"
    with open(papers_yaml_path) as f:
        entries = yaml.safe_load(f) or []
    known_ids = {str(entry["id"]) for entry in entries if "id" in entry}

    jan_2026_ids = {
        str(entry["id"])
        for entry in entries
        if "id" in entry and str(entry.get("date", "")) == "2026-01"
    }
    assert len(jan_2026_ids) == 5

    # Simulate parse_papers() having found exactly those 5 papers again.
    simulated_parsed = [
        {"id": pid, "title": "t", "date": "2026-01", "url": "https://arxiv.org/abs/" + pid}
        for pid in jan_2026_ids
    ]
    new = filter_new(simulated_parsed, known_ids, cutoff="2026-01")

    assert new == []
