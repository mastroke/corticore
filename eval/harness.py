#!/usr/bin/env python3
"""corticore evaluation harness.

Defines the interface future benchmark datasets (LoCoMo, LongMemEval-style)
will plug into: load a dataset of (facts, queries) -> remember the facts ->
reflect -> recall each query -> score whether the right memory came back ->
write a results JSON.

Ships with one tiny synthetic dataset so this runs green with zero external
data. Real datasets belong in `eval/datasets/` (currently empty) and should
be loaded the same way `_synthetic_dataset()` is structured here, so
swapping in LoCoMo/LongMemEval later doesn't change this file's shape.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from corticore import Memory  # noqa: E402
from corticore.embeddings.base import Embedder  # noqa: E402
from corticore.embeddings.local import LocalEmbedder  # noqa: E402
from corticore.stores.sqlite_store import SQLiteStore  # noqa: E402

RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class Query:
    query: str
    expects_substring: str  # a substring that should appear in the top recall


@dataclass
class Dataset:
    name: str
    facts: list[str]
    queries: list[Query]


def _synthetic_dataset() -> Dataset:
    """A minimal built-in dataset: recall correctness + conflict resolution."""
    return Dataset(
        name="synthetic-v0",
        facts=[
            "The user's name is Priya.",
            "Priya prefers dark mode in every app.",
            "The user's favorite programming language is Python.",
            "The user's name is actually Priyanka, not Priya.",
            "The project deadline is March 15th.",
            "The capital of France is Paris.",
        ],
        queries=[
            Query("what is the user's name?", "Priyanka"),
            Query("what theme does the user prefer?", "dark mode"),
            Query("what programming language does the user like?", "Python"),
            Query("when is the project deadline?", "March 15th"),
            Query("what is the capital of France?", "Paris"),
        ],
    )


def run(dataset: Dataset, k: int = 3, embedder: Embedder | None = None) -> dict[str, Any]:
    """Run one dataset through remember -> reflect -> recall and score it.

    `embedder` defaults to the zero-dependency `LocalEmbedder`; pass another
    `Embedder` (e.g. `SentenceTransformerEmbedder`) to benchmark it against
    the same dataset.
    """
    # An in-memory SQLite database keeps each eval run isolated and disk-free.
    mem = Memory(store=SQLiteStore(":memory:"), embedder=embedder or LocalEmbedder())

    for fact in dataset.facts:
        mem.remember(fact)
    report = mem.reflect()

    per_query = []
    hits = 0
    for q in dataset.queries:
        results = mem.recall(q.query, k=k)
        found = any(q.expects_substring.lower() in r.text.lower() for r in results)
        hits += int(found)
        per_query.append(
            {
                "query": q.query,
                "expects_substring": q.expects_substring,
                "found": found,
                "top_results": [
                    {"text": r.text, "score": round(r.score, 4)} for r in results
                ],
            }
        )

    mem.close()
    total = len(dataset.queries)
    return {
        "dataset": dataset.name,
        "facts_remembered": len(dataset.facts),
        "consolidation": {
            "merged": len(report.merged),
            "superseded": len(report.superseded),
            "pruned": len(report.pruned),
        },
        "recall_at_k": {"k": k, "hits": hits, "total": total, "score": hits / total if total else 0.0},
        "queries": per_query,
    }


def main() -> int:
    dataset = _synthetic_dataset()
    result = run(dataset)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{dataset.name}-{int(time.time())}.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"[corticore eval] dataset={dataset.name}")
    print(
        f"[corticore eval] recall@{result['recall_at_k']['k']} = "
        f"{result['recall_at_k']['hits']}/{result['recall_at_k']['total']} "
        f"({result['recall_at_k']['score']:.0%})"
    )
    print(
        f"[corticore eval] consolidation: merged={result['consolidation']['merged']} "
        f"superseded={result['consolidation']['superseded']} pruned={result['consolidation']['pruned']}"
    )
    print(f"[corticore eval] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
