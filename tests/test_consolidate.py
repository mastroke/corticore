import time

from corticore.core.config import Config, ConsolidationConfig, DecayConfig
from corticore.core.types import MemoryItem, MemoryStatus
from corticore.dynamics.consolidate import reflect
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.sqlite_store import SQLiteStore


def make_config(**consolidation_overrides) -> Config:
    return Config(consolidation=ConsolidationConfig(**consolidation_overrides))


def test_reflect_merges_near_identical_memories():
    store = SQLiteStore(":memory:")
    embedder = LocalEmbedder()
    now = time.time()

    text = "The user's favorite color is blue."
    a = MemoryItem(id="a", text=text, embedding=embedder.embed(text), created_at=now - 10)
    b = MemoryItem(id="b", text=text, embedding=embedder.embed(text), created_at=now)
    store.put(a)
    store.put(b)

    report = reflect(store, embedder, make_config())

    assert report.inspected == 2
    assert len(report.merged) == 1
    loser_id, winner_id = report.merged[0]
    assert winner_id == "b"  # newer wins on a tie
    assert loser_id == "a"

    persisted_loser = store.get("a")
    assert persisted_loser.status == MemoryStatus.MERGED
    assert persisted_loser.superseded_by == "b"


def test_reflect_supersedes_conflicting_memories_keeping_higher_salience():
    store = SQLiteStore(":memory:")
    embedder = LocalEmbedder()
    now = time.time()

    # Different text (no keyword overlap) but identical embeddings, so
    # blended similarity lands in the "related, not duplicate" band under a
    # relaxed threshold below — this isolates the winner/loser + status
    # transition logic from the embedder's actual semantics.
    shared_vec = [1.0, 0.0]
    old = MemoryItem(
        id="old", text="alpha bravo charlie", embedding=shared_vec,
        created_at=now - 100, salience=0.4,
    )
    new = MemoryItem(
        id="new", text="delta echo foxtrot", embedding=shared_vec,
        created_at=now, salience=0.9,
    )
    store.put(old)
    store.put(new)

    config = make_config(
        merge_similarity_threshold=0.4,
        duplicate_similarity_threshold=0.9,
    )
    report = reflect(store, embedder, config)

    assert len(report.superseded) == 1
    loser_id, winner_id = report.superseded[0]
    assert winner_id == "new"  # higher salience wins
    assert loser_id == "old"

    persisted_loser = store.get("old")
    assert persisted_loser.status == MemoryStatus.SUPERSEDED
    assert persisted_loser.superseded_by == "new"

    persisted_winner = store.get("new")
    assert persisted_winner.status == MemoryStatus.ACTIVE


def test_reflect_conflict_uses_decayed_salience_not_raw():
    """A frequently-boosted but long-idle memory loses to a fresher correction."""
    store = SQLiteStore(":memory:")
    embedder = LocalEmbedder()
    now = time.time()
    shared_vec = [1.0, 0.0]

    stale_high = MemoryItem(
        id="stale_high",
        text="alpha bravo charlie",
        embedding=shared_vec,
        created_at=now - 10_000,
        last_accessed_at=now - 10_000,
        salience=0.95,  # raw salience looks dominant
    )
    fresh_low = MemoryItem(
        id="fresh_low",
        text="delta echo foxtrot",
        embedding=shared_vec,
        created_at=now,
        last_accessed_at=now,
        salience=0.5,
    )
    store.put(stale_high)
    store.put(fresh_low)

    config = Config(
        decay=DecayConfig(half_life_seconds=100, min_salience=0.0),
        consolidation=ConsolidationConfig(
            merge_similarity_threshold=0.4,
            duplicate_similarity_threshold=0.9,
        ),
    )
    report = reflect(store, embedder, config, now=now)

    assert len(report.superseded) == 1
    loser_id, winner_id = report.superseded[0]
    assert winner_id == "fresh_low"
    assert loser_id == "stale_high"


def test_reflect_prunes_decayed_memories():
    store = SQLiteStore(":memory:")
    embedder = LocalEmbedder()
    now = time.time()

    stale = MemoryItem(
        id="stale", text="an old fact nobody asked about",
        embedding=embedder.embed("an old fact nobody asked about"),
        created_at=now - 1_000_000,
        last_accessed_at=now - 1_000_000,
        salience=1.0,
    )
    store.put(stale)

    config = Config(
        decay=DecayConfig(half_life_seconds=1, min_salience=0.0),
        consolidation=ConsolidationConfig(forget_threshold=0.05),
    )
    report = reflect(store, embedder, config, now=now)

    assert report.pruned == ["stale"]
    assert store.get("stale").status == MemoryStatus.FORGOTTEN


def test_reflect_force_expires_time_bounded_memories_even_at_high_salience():
    store = SQLiteStore(":memory:")
    embedder = LocalEmbedder()
    now = time.time()

    text = "the standup moved to 10am this week"
    expiring = MemoryItem(
        id="expiring",
        text=text,
        embedding=embedder.embed(text),
        created_at=now,
        last_accessed_at=now,
        salience=1.0,  # maximally salient, would never decay-prune on its own
        expires_at=now - 1,  # already in the past
    )
    store.put(expiring)

    # A very slow decay config, so only expiry (not decay) could explain pruning.
    config = Config(
        decay=DecayConfig(half_life_seconds=10_000_000),
        consolidation=ConsolidationConfig(forget_threshold=0.0),
    )
    report = reflect(store, embedder, config, now=now)

    assert report.pruned == ["expiring"]
    persisted = store.get("expiring")
    assert persisted.status == MemoryStatus.FORGOTTEN

    events = store.events_for("expiring")
    assert any(ev.kind == "expired" for ev in events)


def test_reflect_leaves_non_expiring_memories_active():
    store = SQLiteStore(":memory:")
    embedder = LocalEmbedder()
    now = time.time()

    text = "a fact with no expiry"
    item = MemoryItem(
        id="no-expiry",
        text=text,
        embedding=embedder.embed(text),
        created_at=now,
        last_accessed_at=now,
        salience=1.0,
        expires_at=None,
    )
    store.put(item)

    report = reflect(store, embedder, make_config())

    assert not report.changed
    assert store.get("no-expiry").status == MemoryStatus.ACTIVE


def test_reflect_is_noop_on_unrelated_memories():
    store = SQLiteStore(":memory:")
    embedder = LocalEmbedder()

    store.put(MemoryItem(id="a", text="cats are great pets", embedding=embedder.embed("cats are great pets")))
    store.put(MemoryItem(id="b", text="the stock market closed higher today", embedding=embedder.embed("the stock market closed higher today")))

    report = reflect(store, embedder, make_config())

    assert not report.changed
    assert store.get("a").status == MemoryStatus.ACTIVE
    assert store.get("b").status == MemoryStatus.ACTIVE
