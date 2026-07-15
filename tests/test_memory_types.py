import pytest

from corticore import Memory
from corticore.core.types import MEMORY_TYPE_KEY, MemoryType
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.sqlite_store import SQLiteStore


@pytest.fixture
def mem():
    m = Memory(store=SQLiteStore(":memory:"), embedder=LocalEmbedder())
    yield m
    m.close()


def test_memory_type_is_stored_in_metadata(mem):
    mid = mem.remember("Paris is the capital of France", memory_type=MemoryType.SEMANTIC)
    item = mem.store.get(mid)
    assert item.metadata[MEMORY_TYPE_KEY] == "semantic"


def test_recall_filters_by_memory_type(mem):
    mem.remember("user deployed the app on friday", memory_type=MemoryType.EPISODIC)
    mem.remember("to deploy, run make deploy", memory_type=MemoryType.PROCEDURAL)

    results = mem.recall("deploy", filters={MEMORY_TYPE_KEY: "procedural"})

    assert results
    assert all(r.metadata.get(MEMORY_TYPE_KEY) == "procedural" for r in results)


def test_plain_string_memory_type_accepted(mem):
    mid = mem.remember("some rule", memory_type="procedural")
    assert mem.store.get(mid).metadata[MEMORY_TYPE_KEY] == "procedural"


def test_untyped_memory_behaves_as_before(mem):
    mid = mem.remember("an untyped memory")
    assert MEMORY_TYPE_KEY not in mem.store.get(mid).metadata
    assert mem.recall("untyped memory")
