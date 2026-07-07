"""Hybrid retrieval: keyword overlap + embedding similarity, decay-adjusted.

Ranking a candidate combines two signals (weighted by `RetrievalConfig`) and
then multiplies by the memory's current decay factor, so a lexically- and
semantically-relevant match that hasn't been touched in months is still
outranked by a fresher, similarly relevant one. This is the mechanism that
makes "forgetting" observable in `recall()`, not just in `reflect()`.
"""

from __future__ import annotations

import re
import time

from corticore.core.config import Config
from corticore.core.types import MemoryItem, MemoryStatus, RecallResult
from corticore.dynamics.decay import decay_factor
from corticore.embeddings.base import Embedder
from corticore.embeddings.local import cosine_similarity

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def keyword_score(query: str, text: str) -> float:
    """Fraction of `query`'s tokens that also appear in `text` (asymmetric)."""
    q_tokens = set(_TOKEN_RE.findall(query.lower()))
    t_tokens = set(_TOKEN_RE.findall(text.lower()))
    if not q_tokens or not t_tokens:
        return 0.0
    overlap = q_tokens & t_tokens
    return len(overlap) / len(q_tokens)


def retrieve(
    query: str,
    items: list[MemoryItem],
    embedder: Embedder,
    config: Config,
    k: int | None = None,
    now: float | None = None,
) -> list[RecallResult]:
    """Rank active memories against `query` and return the top `k`."""
    now = now if now is not None else time.time()
    k = k if k is not None else config.retrieval.default_k
    query_vec = embedder.embed(query)

    scored: list[RecallResult] = []
    for item in items:
        if item.status != MemoryStatus.ACTIVE:
            continue
        kw = keyword_score(query, item.text)
        sim = cosine_similarity(query_vec, item.embedding)
        decay = decay_factor(item, config.decay, now)
        base = (
            config.retrieval.keyword_weight * kw
            + config.retrieval.similarity_weight * sim
        )
        score = base * decay
        scored.append(
            RecallResult(
                id=item.id,
                text=item.text,
                metadata=item.metadata,
                score=score,
                similarity=sim,
                decay_factor=decay,
                created_at=item.created_at,
            )
        )

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:k]
