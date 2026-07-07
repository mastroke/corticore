"""Tests for the optional Postgres backend.

Skipped entirely (not failed) unless both:
1. `psycopg` is installed (`pip install corticore[postgres]`), and
2. a Postgres server is reachable at `DATABASE_URL` (or the local default
   below).

This is expected to skip in most environments, including this sandbox,
which has neither. Run these against a real Postgres (e.g. `docker run -p
5432:5432 -e POSTGRES_PASSWORD=postgres postgres` + `export DATABASE_URL=...`)
to get real coverage.
"""

from __future__ import annotations

import os
import time

import pytest

pytest.importorskip("psycopg")

from corticore import Memory  # noqa: E402
from corticore.core.types import MemoryItem, TraceEvent  # noqa: E402
from corticore.embeddings.local import LocalEmbedder  # noqa: E402
from corticore.stores.postgres_store import PostgresStore  # noqa: E402

DSN = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)


@pytest.fixture
def store():
    try:
        s = PostgresStore(dsn=DSN)
        s._conn.execute("DELETE FROM events")
        s._conn.execute("DELETE FROM memories")
    except Exception as exc:  # pragma: no cover - depends on external service
        pytest.skip(f"no reachable Postgres at {DSN}: {exc}")
    yield s
    s.close()


def test_put_and_get_roundtrip(store):
    item = MemoryItem(id="pg-roundtrip", text="hello postgres", embedding=[0.1, 0.2])
    store.put(item)

    fetched = store.get("pg-roundtrip")
    assert fetched.text == "hello postgres"
    assert fetched.embedding == [0.1, 0.2]


def test_events_roundtrip(store):
    item = MemoryItem(id="pg-events", text="event test")
    store.put(item)
    store.append_event(
        TraceEvent(kind="stored", at=time.time(), detail="x", data={"memory_id": "pg-events"})
    )

    events = store.events_for("pg-events")
    assert len(events) == 1
    assert events[0].kind == "stored"


def test_delete_removes_item_and_events(store):
    item = MemoryItem(id="pg-delete", text="to delete")
    store.put(item)
    store.append_event(
        TraceEvent(kind="stored", at=time.time(), detail="x", data={"memory_id": "pg-delete"})
    )

    store.delete("pg-delete")

    assert store.get("pg-delete") is None
    assert store.events_for("pg-delete") == []


def test_memory_facade_works_against_postgres(store):
    mem = Memory(store=store, embedder=LocalEmbedder())
    mem.remember("The user's name is Priya.")

    results = mem.recall("what is the user's name?")

    assert results
    assert any("Priya" in r.text for r in results)
