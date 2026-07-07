"""Optional Postgres backend - the first non-default, multi-writer `MemoryStore`.

Mirrors `stores/sqlite_store.SQLiteStore`'s schema and behavior exactly, so
switching between them is just swapping which class you pass to `Memory`.
`SQLiteStore` remains the zero-setup default; this is purely opt-in for
production/shared-state use cases (see ADR 0004).

Install with: pip install corticore[postgres]
"""

from __future__ import annotations

import os
from typing import Any, Optional

from corticore.core.types import MemoryItem, MemoryStatus, TraceEvent
from corticore.stores.base import MemoryStore

_INSTALL_HINT = (
    "PostgresStore requires the 'psycopg' package. "
    "Install it with: pip install corticore[postgres]"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    metadata JSONB NOT NULL,
    embedding JSONB NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    last_accessed_at DOUBLE PRECISION NOT NULL,
    access_count INTEGER NOT NULL,
    salience DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    superseded_by TEXT,
    expires_at DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS events (
    seq SERIAL PRIMARY KEY,
    memory_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    at DOUBLE PRECISION NOT NULL,
    detail TEXT NOT NULL,
    data JSONB NOT NULL
);
"""


class PostgresStore(MemoryStore):
    """Postgres-backed `MemoryStore` for multi-writer/production deployments."""

    def __init__(self, dsn: Optional[str] = None) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Json
        except ImportError as exc:  # pragma: no cover - exercised via importorskip
            raise ImportError(_INSTALL_HINT) from exc

        self._Json = Json

        dsn = dsn or os.environ.get("DATABASE_URL")
        if not dsn:
            raise ValueError(
                "PostgresStore needs a connection string: pass dsn=... or set "
                "DATABASE_URL. See .env.example."
            )

        self._conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
        self._conn.execute(_SCHEMA)

    def put(self, item: MemoryItem) -> None:
        self._conn.execute(
            """
            INSERT INTO memories
                (id, text, metadata, embedding, created_at, last_accessed_at,
                 access_count, salience, status, superseded_by, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
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
                self._Json(item.metadata),
                self._Json(item.embedding),
                item.created_at,
                item.last_accessed_at,
                item.access_count,
                item.salience,
                item.status.value,
                item.superseded_by,
                item.expires_at,
            ),
        )

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE id = %s", (memory_id,)
        ).fetchone()
        return self._row_to_item(row) if row else None

    def delete(self, memory_id: str) -> None:
        self._conn.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
        self._conn.execute("DELETE FROM events WHERE memory_id = %s", (memory_id,))

    def all(self) -> list[MemoryItem]:
        rows = self._conn.execute("SELECT * FROM memories").fetchall()
        return [self._row_to_item(r) for r in rows]

    def append_event(self, event: TraceEvent) -> None:
        memory_id = event.data.get("memory_id", "")
        self._conn.execute(
            "INSERT INTO events (memory_id, kind, at, detail, data) VALUES (%s, %s, %s, %s, %s)",
            (memory_id, event.kind, event.at, event.detail, self._Json(event.data)),
        )

    def events_for(self, memory_id: str) -> list[TraceEvent]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE memory_id = %s ORDER BY seq ASC", (memory_id,)
        ).fetchall()
        return [
            TraceEvent(kind=r["kind"], at=r["at"], detail=r["detail"], data=r["data"])
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_item(row: dict[str, Any]) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            text=row["text"],
            metadata=row["metadata"],
            embedding=row["embedding"],
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
            access_count=row["access_count"],
            salience=row["salience"],
            status=MemoryStatus(row["status"]),
            superseded_by=row["superseded_by"],
            expires_at=row["expires_at"],
        )
