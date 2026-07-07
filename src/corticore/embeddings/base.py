"""Abstract embedding interface — the seam v2 embedders plug into.

`LocalEmbedder` (zero dependencies) is the default. `pip install
corticore[st]` or `corticore[openai]` can register richer embedders that
implement this same `Embedder` contract, so `dynamics/retrieval.py` never
needs to know which one is in use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Embedder(ABC):
    """Turns text into a fixed-length vector of floats."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single string."""

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings. Default: embed one at a time."""
        return [self.embed(t) for t in texts]
