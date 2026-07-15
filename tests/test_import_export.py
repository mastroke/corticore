import pytest

from corticore import Memory
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.sqlite_store import SQLiteStore


def _new_mem():
    return Memory(store=SQLiteStore(":memory:"), embedder=LocalEmbedder())


def _sorted_dump(mem):
    return sorted(
        (
            (i.id, i.text, i.namespace, i.status.value, tuple(sorted(i.metadata.items())))
            for i in mem.store.all()
        )
    )


def test_export_then_import_round_trips_memories(tmp_path):
    src = _new_mem()
    src.remember("alice likes dark mode", metadata={"topic": "ui"}, namespace="alice")
    src.remember("bob likes light mode", namespace="bob")
    src.remember("plain default memory")

    path = str(tmp_path / "dump.jsonl")
    exported = src.export_jsonl(path)
    assert exported == 3

    dst = _new_mem()
    imported = dst.import_jsonl(path)
    assert imported == 3

    assert _sorted_dump(dst) == _sorted_dump(src)

    src.close()
    dst.close()


def test_import_is_idempotent(tmp_path):
    src = _new_mem()
    src.remember("only memory")
    path = str(tmp_path / "dump.jsonl")
    src.export_jsonl(path)

    dst = _new_mem()
    dst.import_jsonl(path)
    dst.import_jsonl(path)  # second import should not duplicate

    assert len(dst.store.all()) == 1

    src.close()
    dst.close()


def test_export_count_matches_store(tmp_path):
    mem = _new_mem()
    for i in range(5):
        mem.remember(f"memory {i}")
    path = str(tmp_path / "dump.jsonl")
    assert mem.export_jsonl(path) == 5
    mem.close()
