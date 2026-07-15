"""Default zero-setup backend: a single SQLite file, no server required.

This is the reference implementation of `MemoryStore`. v2 backends
(Postgres, Neo4j, Qdrant, ...) should be able to satisfy the exact same
interface as a drop-in replacement.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from corticore.core.types import MemoryItem, MemoryStatus, TraceEvent
from corticore.stores.base import MemoryStore
from corticore.stores.migrations import apply_migrations


class SQLiteStore(MemoryStore):
    """SQLite-backed `MemoryStore` — zero external services required."""

    def __init__(self, path: str = "corticore.db") -> None:
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        apply_migrations(self._conn)

    def put(self, item: MemoryItem) -> None:
        self._conn.execute(
            """
            INSERT INTO memories
                (id, text, metadata, embedding, created_at, last_accessed_at,
                 access_count, salience, status, superseded_by, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                metadata=excluded.metadata,
                embedding=excluded.embedding,
                created_at=excluded.created_at,
                last_accessed_at=excluded.last_accessed_at,
                access_count=excluded.access_count,
                salience=excluded.salience,
                status=excluded.status,
                superseded_by=excluded.superseded_by,
                expires_at=excluded.expires_at
            """,
            (
                item.id,
                item.text,
                json.dumps(item.metadata),
                json.dumps(item.embedding),
                item.created_at,
                item.last_accessed_at,
                item.access_count,
                item.salience,
                item.status.value,
                item.superseded_by,
                item.expires_at,
            ),
        )
        self._conn.commit()

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def delete(self, memory_id: str) -> None:
        self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.execute("DELETE FROM events WHERE memory_id = ?", (memory_id,))
        self._conn.commit()

    def all(self) -> list[MemoryItem]:
        rows = self._conn.execute("SELECT * FROM memories").fetchall()
        return [self._row_to_item(r) for r in rows]

    def append_event(self, event: TraceEvent) -> None:
        # memory_id is carried in event.data["memory_id"] by callers.
        memory_id = event.data.get("memory_id", "")
        self._conn.execute(
            "INSERT INTO events (memory_id, kind, at, detail, data) VALUES (?, ?, ?, ?, ?)",
            (memory_id, event.kind, event.at, event.detail, json.dumps(event.data)),
        )
        self._conn.commit()

    def events_for(self, memory_id: str) -> list[TraceEvent]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE memory_id = ? ORDER BY seq ASC", (memory_id,)
        ).fetchall()
        return [
            TraceEvent(
                kind=r["kind"],
                at=r["at"],
                detail=r["detail"],
                data=json.loads(r["data"]),
            )
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            text=row["text"],
            metadata=json.loads(row["metadata"]),
            embedding=json.loads(row["embedding"]),
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
            access_count=row["access_count"],
            salience=row["salience"],
            status=MemoryStatus(row["status"]),
            superseded_by=row["superseded_by"],
            expires_at=row["expires_at"],
        )
