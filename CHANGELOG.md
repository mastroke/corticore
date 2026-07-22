# Changelog

All notable changes to corticore are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versioning is
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The automated Friday release derives the next version deterministically from
the change labels merged during the week: any `breaking` -> major, else any
`feature` -> minor, else `fix` -> patch. Entries accumulate under
`Unreleased` and are moved under a dated version heading at release time.

## [Unreleased]

### Changed

- Release workflow (`.github/workflows/release.yml`): clean-room wheel install
  and `import corticore` smoke test after build and before tag push or PyPI
  publish, mirroring `ci.yml` and `weekend-verifier.yml`.

### Added

- Local Composer-2.5 swarm loop: every role runs as `composer-2.5` via the
  Cursor SDK local runtime against a dedicated checkout; `run_swarm.py
  --runtime local --loop` repeats think→judge→execute cycles inside the
  04:00–09:00 Asia/Kolkata window up to a soft daily commit ceiling, verifies
  (`pytest` + eval gate) before each push to `main`, and on Friday bumps the
  version + CHANGELOG to trigger `.github/workflows/release.yml`. Scheduled by
  a systemd user timer with linger + `--catch-up` so late wakeups still run
  once (`deploy/systemd/`).
- Research scout competitor fallback: when no new paper/note is ready,
  `research_scout` studies peers in `orchestrate/competitors.yml` (mem0,
  letta, zep, langmem, Awesome-Self-Improving-Agents) and proposes a small,
  ADR-compatible port (`kind: competitor`).
- Daily Telegram digest at 09:30 Asia/Kolkata (`orchestrate/report_daily.py`
  + `corticore-swarm-report.timer`): summarizes today's swarm ledger roles and
  commits landed on main; credentials via `TELEGRAM_BOT_TOKEN` /
  `TELEGRAM_CHAT_ID` in `~/.config/corticore-swarm/env`.
- Agent-swarm orchestration under `orchestrate/swarm/`: role-separated Cursor
  thinkers, a judge, a single code-writing executor, and an independent
  blind verifier, coordinated by `orchestrate/run_swarm.py` under a daily
  operating window, fail-closed model validation, a durable run ledger, and
  hard cost caps (see `research/design/adr/0006-agent-swarm-orchestration.md`).
- Deterministic CI gates (`.github/workflows/ci.yml`): test matrix, package
  build + metadata check, clean-room wheel smoke test, and an eval regression
  gate (`eval/check_baseline.py`).
- Automated Friday release pipeline: deterministic release-candidate
  preparation (`orchestrate/prepare_release.py`), a weekend independent
  verifier, and a fail-closed publish workflow using PyPI Trusted Publishing.
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

### Changed

- `corticore.__version__` is now derived from package metadata (single source
  of truth in `pyproject.toml`) instead of a duplicated literal.

## [0.1.0]

- Initial alpha: SQLite backend (default), local embedder (default),
  decay/consolidate/trace dynamics, time-bounded expiry, optional
  sentence-transformers/Azure OpenAI embedders and Postgres backend, and the
  scheduled paper-review-to-PR loop.
