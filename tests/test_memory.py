import time

import pytest

from corticore import Memory
from corticore.core.types import MemoryStatus
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.sqlite_store import SQLiteStore
from corticore.trace.explain import MemoryNotFoundError


@pytest.fixture
def mem():
    m = Memory(store=SQLiteStore(":memory:"), embedder=LocalEmbedder())
    yield m
    m.close()


def test_remember_returns_id(mem):
    memory_id = mem.remember("The user's name is Priya.")
    assert isinstance(memory_id, str) and memory_id


def test_recall_finds_relevant_memory(mem):
    mem.remember("The user's name is Priya.")
    mem.remember("The capital of France is Paris.")

    results = mem.recall("what is the user's name?")
    assert results
    assert any("Priya" in r.text for r in results)


def test_recall_respects_k(mem):
    for i in range(10):
        mem.remember(f"fact number {i} about testing")

    results = mem.recall("fact about testing", k=3)
    assert len(results) <= 3


def test_why_returns_trace_with_stored_event(mem):
    memory_id = mem.remember("The user's name is Priya.")
    trace = mem.why(memory_id)
    assert trace.memory_id == memory_id
    assert any(ev.kind == "stored" for ev in trace.events)


def test_why_raises_for_unknown_id(mem):
    with pytest.raises(MemoryNotFoundError):
        mem.why("does-not-exist")


def test_recall_boosts_access_and_logs_event(mem):
    memory_id = mem.remember("The user's name is Priya.")
    mem.recall("what is the user's name?")

    trace = mem.why(memory_id)
    assert any(ev.kind == "recalled" for ev in trace.events)


def test_reflect_returns_report(mem):
    mem.remember("The user's name is Priya.")
    report = mem.reflect()
    assert report.inspected == 1
    assert not report.changed


def test_remember_with_expires_at_is_force_forgotten_on_reflect(mem):
    now = time.time()
    memory_id = mem.remember("the promo code expires at midnight", expires_at=now - 1)

    mem.reflect()

    trace = mem.why(memory_id)
    assert trace.status == MemoryStatus.FORGOTTEN
    assert any(ev.kind == "expired" for ev in trace.events)


def test_remember_without_expires_at_survives_reflect(mem):
    memory_id = mem.remember("a fact with no deadline")
    mem.reflect()
    trace = mem.why(memory_id)
    assert trace.status == MemoryStatus.ACTIVE


def test_context_manager_closes_store():
    with Memory(store=SQLiteStore(":memory:"), embedder=LocalEmbedder()) as mem:
        mem.remember("hello")
    # closing twice (explicit close then GC) should not raise
