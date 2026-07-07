"""Zero-dependency local embedder.

Uses the hashing trick (a deterministic bag-of-words hashed into a fixed-size
vector, then L2-normalized) so `corticore` has a working, dependency-free
embedding space out of the box. It is not a semantic embedding model — it
captures lexical overlap, not meaning — but it is enough to make `recall()`
useful with zero setup. Swap in `corticore[st]` (sentence-transformers) or
`corticore[openai]` for real semantic embeddings without changing any other
code, since both would implement the same `Embedder` interface.
"""

from __future__ import annotations

import hashlib
import math
import re

from corticore.embeddings.base import Embedder

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class LocalEmbedder(Embedder):
    """Deterministic hashed bag-of-words embedder."""

    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    def _tokenize(self, text: str) -> list[str]:
        return _TOKEN_RE.findall(text.lower())

    def _hash_index(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") % self.dims

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        tokens = self._tokenize(text)
        if not tokens:
            return vector
        for token in tokens:
            idx = self._hash_index(token)
            vector[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]
        return vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors, robust to zero vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
