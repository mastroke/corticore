import pytest

from corticore import Memory
from corticore.core.types import TraceEvent
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.sqlite_store import SQLiteStore


def _mem(on_event):
    return Memory(
        store=SQLiteStore(":memory:"),
        embedder=LocalEmbedder(),
        on_event=on_event,
    )


def test_callback_receives_stored_and_recalled_events():
    seen = []
    mem = _mem(seen.append)
    try:
        mem.remember("the user's name is Priya")  # 1 "stored" event
        mem.recall("what is the user's name?")     # 1 "recalled" event
    finally:
        mem.close()

    kinds = [e.kind for e in seen]
    assert "stored" in kinds
    assert "recalled" in kinds
    assert all(isinstance(e, TraceEvent) for e in seen)


def test_callback_count_matches_recorded_events():
    seen = []
    mem = _mem(seen.append)
    try:
        mid = mem.remember("a fact")
        mem.recall("a fact")
        recorded = mem.why(mid).events
    finally:
        mem.close()

    # Every event visible in the trace for this memory was also delivered to
    # the callback (the callback additionally sees events for other ids).
    assert len(seen) >= len(recorded)
    assert len(seen) >= 2


def test_no_callback_is_the_default():
    mem = Memory(store=SQLiteStore(":memory:"), embedder=LocalEmbedder())
    try:
        mem.remember("no hook installed")  # must not raise
    finally:
        mem.close()


def test_raising_callback_does_not_break_writes():
    def boom(_event):
        raise RuntimeError("monitoring backend down")

    mem = _mem(boom)
    try:
        mid = mem.remember("resilient write")
        assert mem.store.get(mid) is not None
    finally:
        mem.close()
