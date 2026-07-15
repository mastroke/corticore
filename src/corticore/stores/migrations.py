"""Lightweight, dependency-free SQLite schema migrations.

corticore's zero-setup promise means the default store is a plain SQLite
file the caller may have created with an older version of the library. To
let the schema evolve without data loss (and without pulling in a migration
framework), we track the schema version in SQLite's built-in
``PRAGMA user_version`` and apply ordered, idempotent migration steps on
connect.
"""

from __future__ import annotations

import sqlite3
from typing import Callable

Migration = Callable[[sqlite3.Connection], None]


def _migration_001_base_schema(conn: sqlite3.Connection) -> None:
    """Create the initial ``memories`` and ``events`` tables.

    Uses ``IF NOT EXISTS`` so it is a no-op on databases that already have
    these tables from a pre-migrations release of corticore.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL,
            metadata TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at REAL NOT NULL,
            last_accessed_at REAL NOT NULL,
            access_count INTEGER NOT NULL,
            salience REAL NOT NULL,
            status TEXT NOT NULL,
            superseded_by TEXT,
            expires_at REAL
        );

        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            at REAL NOT NULL,
            detail TEXT NOT NULL,
            data TEXT NOT NULL
        );
        """
    )


def _migration_002_add_namespace(conn: sqlite3.Connection) -> None:
    """Add the ``namespace`` column for multi-tenant isolation (F002).

    Existing rows default to ``'default'`` so data written before namespaces
    stays in the single implicit namespace.
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()]
    if "namespace" not in cols:
        conn.execute(
            "ALTER TABLE memories ADD COLUMN namespace TEXT NOT NULL DEFAULT 'default'"
        )


# Ordered registry: index i applies the migration that upgrades the schema
# from version i to version i+1. Append new migrations; never reorder or edit
# a shipped one.
MIGRATIONS: list[Migration] = [
    _migration_001_base_schema,
    _migration_002_add_namespace,
]

LATEST_VERSION = len(MIGRATIONS)


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version recorded in ``PRAGMA user_version`` (0 if unset)."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row is not None else 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Persist ``version`` into ``PRAGMA user_version``.

    ``user_version`` does not accept a bound parameter, so the integer is
    formatted directly; callers must only ever pass trusted ints from the
    migration registry.
    """
    conn.execute(f"PRAGMA user_version = {int(version)}")


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Bring ``conn`` up to ``LATEST_VERSION``, running only pending steps.

    Returns the schema version after migrating. Each migration and its
    version bump commit together, so an interrupted upgrade never leaves the
    recorded version ahead of the applied schema.
    """
    current = get_schema_version(conn)
    if current > LATEST_VERSION:
        raise RuntimeError(
            f"database schema version {current} is newer than this corticore "
            f"build supports (max {LATEST_VERSION}); upgrade corticore"
        )
    for version in range(current, LATEST_VERSION):
        MIGRATIONS[version](conn)
        set_schema_version(conn, version + 1)
        conn.commit()
    return LATEST_VERSION
