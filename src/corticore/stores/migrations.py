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
