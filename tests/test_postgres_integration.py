"""Postgres integration tests (F009).

These exercise the real `PostgresStore` against a live database. They are
skipped automatically unless a Postgres is reachable, so the default
`pytest` run stays green and dependency-free:

- Set `CORTICORE_TEST_PG_DSN` to point at an existing database, OR
- Have Docker installed and running, in which case a throwaway
  `postgres:16-alpine` container is started and torn down per module.

Requires the `postgres` extra: ``pip install corticore[postgres]``.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("psycopg_pool")

from corticore.stores.postgres_store import PostgresStore  # noqa: E402


def _docker_available() -> bool:
    from shutil import which

    if which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "info"], capture_output=True, timeout=15, check=True
        )
        return True
    except Exception:
        return False


def _free_port() -> int:
    s = socket.socket()
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def pg_dsn():
    existing = os.environ.get("CORTICORE_TEST_PG_DSN")
    if existing:
        yield existing
        return

    if not _docker_available():
        pytest.skip(
            "no Postgres available: set CORTICORE_TEST_PG_DSN or run Docker"
        )

    name = f"corticore-test-{uuid.uuid4().hex[:8]}"
    port = _free_port()
    subprocess.run(
        [
            "docker", "run", "-d", "--rm", "--name", name,
            "-e", "POSTGRES_PASSWORD=corticore",
            "-e", "POSTGRES_DB=corticore",
            "-p", f"{port}:5432",
            "postgres:16-alpine",
        ],
        check=True,
        capture_output=True,
    )
    dsn = f"postgresql://postgres:corticore@localhost:{port}/corticore"
    try:
        deadline = time.time() + 60
        while True:
            try:
                psycopg.connect(dsn, connect_timeout=3).close()
                break
            except Exception:
                if time.time() > deadline:
                    raise
                time.sleep(1)
        yield dsn
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True)


@pytest.fixture
def store(pg_dsn):
    s = PostgresStore(pg_dsn, min_size=1, max_size=5)
    # Isolate each test from prior data in a reused external database.
    s._run(lambda cur: cur.execute("TRUNCATE memories, events"))
    yield s
    s.close()


def test_connectivity_and_schema(store):
    # Schema (with the F002 namespace column) must exist after construction.
    cols = store._run(
        lambda cur: cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'memories'"
        ).fetchall()
    )
    names = {row["column_name"] for row in cols}
    assert {"id", "text", "namespace", "metadata"} <= names
