"""Smoke test: Memory works with any Embedder implementation, not just the
default. This is the contract the F004 benchmark relies on when swapping in
SentenceTransformerEmbedder."""

from corticore import Memory
from corticore.embeddings.base import Embedder
from corticore.stores.sqlite_store import SQLiteStore


class ConstantEmbedder(Embedder):
    """A trivial deterministic embedder used to prove the seam is swappable."""

    def __init__(self, dims: int = 8) -> None:
        self.dims = dims

    def embed(self, text: str) -> list[float]:
        # Length-based bucketing: enough signal for a smoke test, no deps.
        vec = [0.0] * self.dims
        vec[len(text) % self.dims] = 1.0
        return vec


def test_memory_accepts_a_custom_embedder():
    mem = Memory(store=SQLiteStore(":memory:"), embedder=ConstantEmbedder())
    try:
        mid = mem.remember("hello world")
        assert mem.store.get(mid).embedding[len("hello world") % 8] == 1.0
        results = mem.recall("hello world")
        assert isinstance(results, list)
    finally:
        mem.close()


def test_harness_run_accepts_an_embedder():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
    from harness import _synthetic_dataset, run

    result = run(_synthetic_dataset(), embedder=ConstantEmbedder())
    assert result["recall_at_k"]["total"] == 5
