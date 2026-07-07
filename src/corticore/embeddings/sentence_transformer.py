"""Optional semantic embedder backed by `sentence-transformers`.

This is a real semantic embedding model, unlike the zero-dependency
`LocalEmbedder`, at the cost of a heavier dependency (a model download and
a torch/transformers install). Not imported anywhere by default — importing
this module is only reachable if the caller explicitly asks for it, so the
base `corticore` package stays dependency-free.

Install with: pip install corticore[st]
"""

from __future__ import annotations

from typing import Any

from corticore.embeddings.base import Embedder

_INSTALL_HINT = (
    "SentenceTransformerEmbedder requires the 'sentence-transformers' package. "
    "Install it with: pip install corticore[st]"
)


class SentenceTransformerEmbedder(Embedder):
    """Wraps a `sentence-transformers` model behind the `Embedder` interface."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", **model_kwargs: Any) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised via importorskip
            raise ImportError(_INSTALL_HINT) from exc

        self.model_name = model_name
        self._model = SentenceTransformer(model_name, **model_kwargs)

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return vector.tolist()

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vectors.tolist()
