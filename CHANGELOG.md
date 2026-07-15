# Changelog

All notable changes to corticore are documented here. This project adheres to
[Semantic Versioning](https://semver.org/) and the format is loosely based on
[Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Real Hugging Face dataset evaluation: `eval/datasets/squad.py` loads SQuAD
  v1.1 (`rajpurkar/squad`) into the harness's `(facts, queries,
  expects_substring)` shape, and `eval/harness.py` gained
  `--dataset {synthetic,squad}` plus `--limit/--split/--k` flags. The split is
  shuffled with a fixed seed for a representative distractor pool. Needs the
  new optional `hf` extra (`pip install corticore[hf]`, installs `datasets`);
  the synthetic default stays zero-dependency and offline. Baseline recorded in
  `eval/BASELINE.md` (recall@3 = 292/493 on 500 shuffled validation rows with
  the default `LocalEmbedder`).
- CLI inspection tool (`F010`): a `corticore` console command with
  `list`, `recall`, `why`, and `reflect` subcommands for inspecting a memory
  store from the shell. Registered via `project.scripts`.
- Postgres store hardening (`F009`): `PostgresStore` now pools connections
  (`min_size`/`max_size`) and retries transient connection, serialization, and
  deadlock errors with exponential backoff. Its schema gained the `namespace`
  column for parity with SQLite (auto-migrated via `ADD COLUMN IF NOT EXISTS`).
  Adds Docker-based integration tests (CRUD + concurrent writes) that skip when
  no database is reachable; the `postgres` extra now includes the connection
  pool.
- Semantic embedder benchmark (`F004`): `eval/benchmark_embedders.py` compares
  the default `LocalEmbedder` with `SentenceTransformerEmbedder` on the eval
  dataset; `harness.run()` now accepts an `embedder`. Measured result recorded
  in `eval/BASELINE.md`: semantic embeddings reach recall@3 = 5/5 vs the
  lexical baseline's 4/5, closing the paraphrase gap.
- Observability hooks (`F008`): an optional `on_event` callback on `Memory`
  receives every recorded `TraceEvent` (including events emitted inside
  `reflect()`) for logging/metrics/tracing. Callback exceptions are isolated
  from the write path. No-op by default.
- Async memory API (`F005`): `aremember`, `arecall`, and `areflect` wrap the
  sync methods with `asyncio.to_thread` so async agent runtimes are not
  blocked. No new dependencies; sync remains the default.
- Structured memory types (`F007`): optional `memory_type`
  (semantic/episodic/procedural, see `MemoryType`) tags a memory's cognitive
  category under `metadata`, filterable via `recall(filters=...)`. Untyped
  memories are unaffected. `MemoryType` is exported from the package root.
- JSONL import/export (`F006`): `export_jsonl(path)` and `import_jsonl(path)`
  serialize a store's memories to/from JSON Lines for backup, migration, and
  debugging. Import is idempotent (upsert by id).
- Namespaced memories (`F002`): `remember(..., namespace=...)` and
  `recall(..., namespace=...)` isolate memories per user/session/agent in a
  single store. Namespaces never leak across `recall()` and are never
  consolidated together by `reflect()`. Defaults to `"default"`, preserving
  single-tenant behavior.
- SQLite schema migrations (`F003`): the default store tracks its schema
  version via `PRAGMA user_version` and applies ordered, idempotent
  migrations on connect, upgrading older databases in place without data loss.
- Feature backlog workflow: a local (gitignored) `feature-list.csv` backlog and
  a `corticore-feature-builder` project skill that drives researched,
  vision-checked, test-backed feature work, plus a `ROADMAP.md`.
- Metadata-filtered recall (`F001`): `recall(query, filters={...})` narrows
  candidates to memories whose metadata matches every key/value pair before
  scoring. Omitting `filters` preserves prior behavior exactly.
