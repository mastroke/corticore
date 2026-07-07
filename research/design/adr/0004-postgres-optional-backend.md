# ADR 0004: Postgres as the first optional, non-default backend

## Status

Accepted (v0.1, depth round)

## Context

ADR 0001 fixed `SQLiteStore` as the zero-setup default, which is correct
for the target "a single agent's local memory" use case but has a known
limit: SQLite is effectively single-writer, so it doesn't fit a shared
memory store accessed by multiple agent processes or a production service
with concurrent writers. Rather than stretch SQLite to cover that case (or
delay it until a "v2 rewrite"), the `stores/base.py::MemoryStore` interface
(ADR 0001) was built specifically so a second backend could be added
without touching `Memory`, `dynamics/`, or `trace/`.

## Decision

Add `stores/postgres_store.py::PostgresStore`, implementing the exact same
`MemoryStore` interface as `SQLiteStore`, using `psycopg` (v3) behind a new
`postgres` extra (`pip install corticore[postgres]`). Schema mirrors
SQLite's `memories`/`events` tables field-for-field, including the
`expires_at` column introduced in ADR 0003 — Postgres support is added
*after* Foresight, not before, so there's no migration to backport.

`PostgresStore` takes a `dsn` argument or falls back to the `DATABASE_URL`
environment variable — no different a pattern than the Azure embedder's
credential handling (ADR-adjacent, see `embeddings/azure_openai.py`), for
consistency across all optional backends.

`SQLiteStore` remains the default returned by `Memory()` when no `store=`
is passed. Choosing Postgres is always explicit:
`Memory(store=PostgresStore(dsn=...))`.

## Consequences

- Tests in `tests/test_postgres_store.py` skip (not fail) when `psycopg`
  isn't installed or no Postgres is reachable — true in this sandbox and in
  most contributors' local setups without a running server. Real coverage
  requires a Postgres instance (documented in the test file's docstring).
- JSON columns (`metadata`, `embedding`, event `data`) use `psycopg`'s
  `Json` adapter rather than manual `json.dumps`/`json.loads`, so
  serialization is handled by the driver consistently with its type system
  rather than by convention.
- This does not add connection pooling, retries, or migrations — those are
  explicitly deferred until there's a concrete production deployment
  driving the requirements, to avoid speculative infrastructure work.
- CompassMem/MAGMA (see their notes in `research/notes/`) both assume
  graph-capable storage; Postgres does not change that calculus; a future
  graph backend remains a separate, later decision.
