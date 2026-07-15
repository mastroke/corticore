"""Optional Postgres backend - the first non-default, multi-writer `MemoryStore`.

Mirrors `stores/sqlite_store.SQLiteStore`'s schema and behavior exactly, so
switching between them is just swapping which class you pass to `Memory`.
`SQLiteStore` remains the zero-setup default; this is purely opt-in for
production/shared-state use cases (see ADR 0004).

Install with: pip install corticore[postgres]
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from corticore.core.types import MemoryItem, MemoryStatus, TraceEvent
from corticore.stores.base import MemoryStore

_INSTALL_HINT = (
    "PostgresStore requires the 'psycopg' and 'psycopg_pool' packages. "
    "Install them with: pip install corticore[postgres]"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'default',
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

# Bring pre-namespace Postgres databases up to the current schema. Idempotent.
_MIGRATE = (
    "ALTER TABLE memories ADD COLUMN IF NOT EXISTS namespace TEXT NOT NULL "
    "DEFAULT 'default'"
)


class PostgresStore(MemoryStore):
    """Postgres-backed `MemoryStore` for multi-writer/production deployments.

    Connections are managed by a `psycopg_pool.ConnectionPool` so many
    concurrent writers share a bounded set of connections instead of each
    holding one open indefinitely. Transient connection failures are retried
    with exponential backoff (see `_run`).
    """

    def __init__(
        self,
        dsn: Optional[str] = None,
        *,
        min_size: int = 1,
        max_size: int = 10,
        max_retries: int = 3,
        retry_backoff: float = 0.1,
    ) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg.types.json import Json
            from psycopg_pool import ConnectionPool
        except ImportError as exc:  # pragma: no cover - exercised via importorskip
            raise ImportError(_INSTALL_HINT) from exc

        self._psycopg = psycopg
        self._Json = Json
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff

        dsn = dsn or os.environ.get("DATABASE_URL")
        if not dsn:
            raise ValueError(
                "PostgresStore needs a connection string: pass dsn=... or set "
                "DATABASE_URL. See .env.example."
            )

        self._pool = ConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row, "autocommit": True},
            open=True,
        )
        self._run(lambda cur: cur.execute(_SCHEMA))
        self._run(lambda cur: cur.execute(_MIGRATE))

    def _run(self, fn: Any) -> Any:
        """Borrow a pooled connection, run `fn(cursor)`, retry transient errors.

        `fn` receives a cursor and returns whatever the caller needs (e.g. a
        fetched row). Only `psycopg.OperationalError` (dropped/again-later
        connections) is retried; logic errors propagate immediately.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                with self._pool.connection() as conn:
                    with conn.cursor() as cur:
                        return fn(cur)
            except self._psycopg.OperationalError as exc:
                last_exc = exc
                if attempt == self._max_retries - 1:
                    break
                time.sleep(self._retry_backoff * (2 ** attempt))
        raise last_exc  # type: ignore[misc]

    def put(self, item: MemoryItem) -> None:
        self._run(
            lambda cur: cur.execute(
                """
                INSERT INTO memories
                    (id, text, namespace, metadata, embedding, created_at,
                     last_accessed_at, access_count, salience, status,
                     superseded_by, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    text=EXCLUDED.text,
                    namespace=EXCLUDED.namespace,
                    metadata=EXCLUDED.metadata,
                    embedding=EXCLUDED.embedding,
                    created_at=EXCLUDED.created_at,
                    last_accessed_at=EXCLUDED.last_accessed_at,
                    access_count=EXCLUDED.access_count,
                    salience=EXCLUDED.salience,
                    status=EXCLUDED.status,
                    superseded_by=EXCLUDED.superseded_by,
                    expires_at=EXCLUDED.expires_at
                """,
                (
                    item.id,
                    item.text,
                    item.namespace,
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
        )

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        row = self._run(
            lambda cur: cur.execute(
                "SELECT * FROM memories WHERE id = %s", (memory_id,)
            ).fetchone()
        )
        return self._row_to_item(row) if row else None

    def delete(self, memory_id: str) -> None:
        def _delete(cur: Any) -> None:
            cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
            cur.execute("DELETE FROM events WHERE memory_id = %s", (memory_id,))

        self._run(_delete)

    def all(self) -> list[MemoryItem]:
        rows = self._run(lambda cur: cur.execute("SELECT * FROM memories").fetchall())
        return [self._row_to_item(r) for r in rows]

    def append_event(self, event: TraceEvent) -> None:
        memory_id = event.data.get("memory_id", "")
        self._run(
            lambda cur: cur.execute(
                "INSERT INTO events (memory_id, kind, at, detail, data) "
                "VALUES (%s, %s, %s, %s, %s)",
                (memory_id, event.kind, event.at, event.detail, self._Json(event.data)),
            )
        )

    def events_for(self, memory_id: str) -> list[TraceEvent]:
        rows = self._run(
            lambda cur: cur.execute(
                "SELECT * FROM events WHERE memory_id = %s ORDER BY seq ASC",
                (memory_id,),
            ).fetchall()
        )
        return [
            TraceEvent(kind=r["kind"], at=r["at"], detail=r["detail"], data=r["data"])
            for r in rows
        ]

    def close(self) -> None:
        self._pool.close()

    @staticmethod
    def _row_to_item(row: dict[str, Any]) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            text=row["text"],
            namespace=row.get("namespace", "default"),
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
