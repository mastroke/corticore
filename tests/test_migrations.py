import json
import sqlite3
import time

from corticore.stores.migrations import (
    LATEST_VERSION,
    apply_migrations,
    get_schema_version,
)
from corticore.stores.sqlite_store import SQLiteStore


def _make_legacy_v0_db(path: str) -> None:
    """Simulate a database created by a pre-migrations corticore release.

    It has the tables and a row but user_version is still 0, mimicking a file
    written before schema versioning existed.
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE memories (
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
        CREATE TABLE events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            at REAL NOT NULL,
            detail TEXT NOT NULL,
            data TEXT NOT NULL
        );
        """
    )
    now = time.time()
    conn.execute(
        "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("m1", "legacy fact", json.dumps({}), json.dumps([0.1]), now, now, 0, 1.0, "active", None, None),
    )
    conn.commit()
    conn.close()


def test_migrating_existing_v0_db_preserves_data(tmp_path):
    db = str(tmp_path / "legacy.db")
    _make_legacy_v0_db(db)

    store = SQLiteStore(db)
    try:
        item = store.get("m1")
        assert item is not None
        assert item.text == "legacy fact"
        assert get_schema_version(store._conn) == LATEST_VERSION
    finally:
        store.close()


def test_fresh_db_is_created_at_latest_version(tmp_path):
    db = str(tmp_path / "fresh.db")
    store = SQLiteStore(db)
    try:
        assert get_schema_version(store._conn) == LATEST_VERSION
        assert store.all() == []
    finally:
        store.close()


def test_apply_migrations_is_idempotent(tmp_path):
    db = str(tmp_path / "idem.db")
    conn = sqlite3.connect(db)
    assert apply_migrations(conn) == LATEST_VERSION
    assert apply_migrations(conn) == LATEST_VERSION
    conn.close()
