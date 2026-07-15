"""Tests for the real Hugging Face SQuAD eval loader (eval/datasets/squad.py).

Skipped automatically when the optional `hf` extra isn't installed
(`pip install corticore[hf]`) or when the Hugging Face Hub isn't reachable, so
the default `pytest` run stays green and offline. Mirrors the skip-if-missing
pattern used for the embedder/store extras.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("datasets")

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "eval"))
sys.path.insert(0, str(_REPO_ROOT / "eval" / "datasets"))

from harness import run  # noqa: E402
from squad import _split_sentences, load_squad  # noqa: E402


def test_split_sentences_is_dependency_free():
    text = "First fact here. Second one? Third one! Trailing"
    assert _split_sentences(text) == [
        "First fact here.",
        "Second one?",
        "Third one!",
        "Trailing",
    ]


def _load_small_squad():
    try:
        return load_squad(limit=5)
    except Exception as exc:  # network/hub error, offline CI, rate limit
        pytest.skip(f"Hugging Face SQuAD not reachable: {exc}")


def test_load_squad_maps_into_the_harness_shape():
    dataset = _load_small_squad()

    assert dataset.name.startswith("squad:")
    assert dataset.facts, "expected context sentences as facts"
    assert dataset.queries, "expected questions as queries"
    # answerable filter (default) guarantees each gold span is stored somewhere.
    lowered = [f.lower() for f in dataset.facts]
    for q in dataset.queries:
        assert any(q.expects_substring.lower() in f for f in lowered)


def test_squad_runs_through_the_harness():
    dataset = _load_small_squad()
    result = run(dataset, k=3)

    assert result["facts_remembered"] == len(dataset.facts)
    assert result["recall_at_k"]["total"] == len(dataset.queries)
    assert 0 <= result["recall_at_k"]["hits"] <= len(dataset.queries)
