#!/usr/bin/env python3
"""Benchmark embedders against the built-in eval dataset (F004).

Runs the same `harness` dataset through each available embedder and prints a
recall@k comparison. The default `LocalEmbedder` (lexical hashing) always
runs; `SentenceTransformerEmbedder` runs only if `corticore[st]` is installed,
so this script never fails just because the heavy optional dependency is
absent.

Usage:
    PYTHONPATH=src python eval/benchmark_embedders.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))
sys.path.insert(0, str(_HERE))

from corticore.embeddings.local import LocalEmbedder  # noqa: E402
from harness import _synthetic_dataset, run  # noqa: E402


def _load_sentence_transformer():
    """Return a SentenceTransformerEmbedder, or None if the extra is missing."""
    try:
        from corticore.embeddings.sentence_transformer import (
            SentenceTransformerEmbedder,
        )

        return SentenceTransformerEmbedder()
    except Exception as exc:  # ImportError, or model download failure offline
        print(f"[benchmark] skipping sentence-transformers: {exc}")
        return None


def main() -> int:
    dataset = _synthetic_dataset()

    candidates = [("LocalEmbedder", LocalEmbedder())]
    st = _load_sentence_transformer()
    if st is not None:
        candidates.append((f"SentenceTransformerEmbedder({st.model_name})", st))

    print(f"[benchmark] dataset={dataset.name}\n")
    print(f"{'embedder':<45} {'recall@3':>10} {'seconds':>10}")
    print("-" * 67)
    for name, embedder in candidates:
        started = time.time()
        result = run(dataset, embedder=embedder)
        elapsed = time.time() - started
        score = result["recall_at_k"]
        print(f"{name:<45} {score['hits']}/{score['total']:>8} {elapsed:>10.2f}")

    if st is None:
        print(
            "\n[benchmark] Only LocalEmbedder ran. To benchmark semantic "
            "embeddings:\n    pip install corticore[st]\n    "
            "PYTHONPATH=src python eval/benchmark_embedders.py"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
