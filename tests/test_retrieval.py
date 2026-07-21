"""Unit tests for hybrid retrieval ranking and filters."""

from __future__ import annotations

import time

from corticore.core.config import Config
from corticore.core.types import MemoryItem, MemoryStatus
from corticore.dynamics.retrieval import keyword_score, matches_filters, retrieve
from corticore.embeddings.local import LocalEmbedder


def test_keyword_score_asymmetric_overlap():
    assert keyword_score("favorite color blue", "the favorite color is blue") == 1.0
    assert keyword_score("favorite color blue", "favorite color") == 2 / 3
    assert keyword_score("", "anything") == 0.0


def test_matches_filters_requires_every_pair():
    item = MemoryItem(
        id="x",
        text="hi",
        embedding=[0.0],
        created_at=0.0,
        metadata={"user_id": "alice", "env": "prod"},
    )
    assert matches_filters(item, None)
    assert matches_filters(item, {})
    assert matches_filters(item, {"user_id": "alice"})
    assert not matches_filters(item, {"user_id": "bob"})
    assert not matches_filters(item, {"user_id": "alice", "env": "staging"})


def test_retrieve_skips_expired_active_memories():
    embedder = LocalEmbedder()
    now = time.time()
    live = MemoryItem(
        id="live",
        text="the promo code is SAVE10",
        embedding=embedder.embed("the promo code is SAVE10"),
        created_at=now - 10,
        expires_at=now + 3600,
    )
    expired = MemoryItem(
        id="expired",
        text="the promo code is OLD99",
        embedding=embedder.embed("the promo code is OLD99"),
        created_at=now - 10,
        expires_at=now - 1,
    )
    results = retrieve(
        "promo code",
        [live, expired],
        embedder,
        Config(),
        k=5,
        now=now,
    )
    ids = {r.id for r in results}
    assert "live" in ids
    assert "expired" not in ids


def test_retrieve_respects_namespace_and_inactive():
    embedder = LocalEmbedder()
    now = time.time()
    text = "deployment key rotated weekly"
    a = MemoryItem(
        id="a",
        text=text,
        embedding=embedder.embed(text),
        created_at=now,
        namespace="alice",
    )
    b = MemoryItem(
        id="b",
        text=text,
        embedding=embedder.embed(text),
        created_at=now,
        namespace="bob",
    )
    forgotten = MemoryItem(
        id="c",
        text=text,
        embedding=embedder.embed(text),
        created_at=now,
        namespace="alice",
        status=MemoryStatus.FORGOTTEN,
    )
    results = retrieve(
        "deployment key",
        [a, b, forgotten],
        embedder,
        Config(),
        k=5,
        now=now,
        namespace="alice",
    )
    assert [r.id for r in results] == ["a"]
