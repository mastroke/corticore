# corticore

A memory layer for AI agents that runs in 60 seconds — no server, no vector
database, no graph database. And unlike most memory layers, it **forgets on
purpose** and **shows its work**.

```bash
pip install corticore
```

```python
from corticore import Memory

mem = Memory("agent.db")

mem.remember("The user's name is Priya.")
mem.remember("Priya prefers dark mode.")
mem.remember("Priya's name is actually Priyanka.")  # contradicts the first

mem.reflect()  # consolidates: dedups, merges, resolves the name conflict

results = mem.recall("what does the user prefer?")
for r in results:
    print(r.text, r.score)

print(mem.why(results[0].id))  # inspect exactly why this memory was recalled
```

## Why corticore

Every other agent-memory library makes you stand up infrastructure before you
can write a line of application code — a graph database, a vector database, a
running server. corticore's default backend is a single SQLite file and a
zero-dependency local embedder, so `pip install corticore` is the entire
setup.

Beyond setup cost, the field has converged on retrieval and largely ignored
three things human memory does well:

| Gap in existing memory layers | corticore's answer |
| --- | --- |
| Memories only ever accumulate | `dynamics/decay.py` — recency + salience decay, so stale/unused memories fade and get pruned |
| New facts are appended, never reconciled | `dynamics/consolidate.py` — `reflect()` dedups, merges, and resolves contradictions |
| Recall is a black box | `trace/explain.py` — `why(id)` returns the full reasoning trace behind a memory |

This positioning is grounded in a running survey of the agent-memory
literature — see [`research/`](research/) for the paper trail that justifies
every design decision.

## API

- `remember(text, metadata=None, expires_at=None) -> id` — store a memory.
  `expires_at` (epoch seconds) is an optional time-bounded "Foresight"
  deadline — see [ADR 0003](research/design/adr/0003-time-bounded-foresight-memories.md).
- `recall(query, k=5) -> list[RecallResult]` — decay-adjusted hybrid retrieval.
- `reflect() -> ConsolidationReport` — dedup, merge, resolve conflicts, expire, prune.
- `why(memory_id) -> Trace` — explain a memory's storage/decay/merge history.

## Optional extras

The default `Memory("agent.db")` needs nothing beyond the standard library.
Everything below is opt-in and swaps in behind the same interfaces
(`stores/base.py::MemoryStore`, `embeddings/base.py::Embedder`) — no change
to your calling code beyond the `Memory(...)` constructor arguments.

```bash
pip install corticore[st]        # local semantic embeddings (sentence-transformers)
pip install corticore[openai]    # Azure OpenAI embeddings
pip install corticore[postgres]  # multi-writer / production storage backend
```

```python
from corticore import Memory
from corticore.embeddings.sentence_transformer import SentenceTransformerEmbedder

mem = Memory("agent.db", embedder=SentenceTransformerEmbedder())
```

```python
# Azure OpenAI embeddings - reads credentials from environment variables,
# never hardcoded. Copy .env.example to .env and fill in your own values.
from corticore.embeddings.azure_openai import AzureOpenAIEmbedder

embedder = AzureOpenAIEmbedder(deployment="your-embedding-deployment")
mem = Memory("agent.db", embedder=embedder)
```

```python
# Postgres backend for shared/production state (SQLite remains the default).
from corticore.stores.postgres_store import PostgresStore

mem = Memory(store=PostgresStore(dsn="postgresql://..."))
```

## Automated research loop

`.github/workflows/paper-loop.yml` runs weekly (and on manual dispatch):
it checks [Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
for papers dated 2026-01 or later that aren't in
[`research/papers.yaml`](research/papers.yaml) yet, and — only if it finds
any — launches a Cursor cloud agent to review them, write notes, decide
adopt/defer/reject, implement anything adopted (with tests + a new ADR),
check the result against [`eval/BASELINE.md`](eval/BASELINE.md), and open a
PR. It never pushes to `main` directly; a human always reviews the PR. See
[ADR 0005](research/design/adr/0005-scheduled-cloud-agent-research-loop.md)
for the full reasoning, and `orchestrate/` for the scripts and prompt.

To activate it on your own fork/clone:

1. Add a `CURSOR_API_KEY` repository secret (Settings → Secrets and
   variables → Actions).
2. Grant Cursor's GitHub integration access to the repo (one-time setup at
   [cursor.com](https://cursor.com), needed for `auto_create_pr` to open PRs).

You can preview what the loop would do without spending an API call:

```bash
pip install corticore[orchestrate]
python orchestrate/check_new_papers.py           # real network check, no API key needed
python orchestrate/run_cloud_agent.py --dry-run  # prints the prompt, doesn't launch anything
```

## Observability

Pass an `on_event` callback to receive every trace event corticore records
(stored, recalled, merged, forgotten, ...) and forward it to your logs,
metrics, or tracing backend. The callback runs after each event is durably
recorded, and a raising callback never breaks the write path.

```python
import logging

def to_log(event):
    logging.info("corticore %s: %s", event.kind, event.detail)

mem = Memory("agent.db", on_event=to_log)
```

Omit `on_event` (the default) for zero-overhead, zero-setup usage.

## Async API

For async agent runtimes, `aremember`, `arecall`, and `areflect` mirror their
sync counterparts and run the blocking work in a worker thread so they never
block the event loop:

```python
mid = await mem.aremember("the user prefers dark mode", namespace="alice")
results = await mem.arecall("preferences", namespace="alice")
report = await mem.areflect()
```

The synchronous API remains the primary, zero-dependency default.

## Memory types

Optionally tag a memory's cognitive category — `semantic` (facts),
`episodic` (events), or `procedural` (how-to) — and filter recall by it. This
is a convention over `metadata`, so untyped memories are unaffected.

```python
from corticore import MemoryType

mem.remember("Paris is the capital of France", memory_type=MemoryType.SEMANTIC)
mem.remember("to deploy, run make deploy", memory_type=MemoryType.PROCEDURAL)

mem.recall("deploy", filters={"memory_type": "procedural"})
```

## Command-line tool

Installing corticore adds a `corticore` CLI for inspecting a store without
writing code:

```bash
corticore --db agent.db list                 # list memories (most salient first)
corticore --db agent.db recall "user name?"  # run a recall query
corticore --db agent.db why <memory_id>       # show a memory's full trace
corticore --db agent.db reflect               # run a consolidation pass
```

`list` and `recall` accept `--namespace`; the default database is
`corticore.db`.

## Backup and migration

Export a store to JSON Lines and import it back, for backups, moving between
stores, or inspecting state:

```python
mem.export_jsonl("backup.jsonl")   # one memory per line

restored = Memory("fresh.db")
restored.import_jsonl("backup.jsonl")  # idempotent; re-import overwrites by id
```

## Namespaces

Isolate memories per user, session, or agent by passing a `namespace`. This
keeps one shared store safe for multi-tenant use without any extra
infrastructure. Memories in different namespaces never surface in each
other's `recall()` results, and `reflect()` never consolidates across
namespace boundaries.

```python
mem.remember("Alice prefers dark mode", namespace="alice")
mem.remember("Bob prefers light mode", namespace="bob")

mem.recall("theme preference", namespace="alice")  # only Alice's memories
mem.recall("theme preference", namespace=None)      # search every namespace
```

`namespace` defaults to `"default"`, so existing single-tenant code keeps
working unchanged.

## Postgres backend

For multi-writer / production deployments, use the optional Postgres store
instead of the default SQLite file:

```bash
pip install corticore[postgres]
```

```python
from corticore import Memory
from corticore.stores.postgres_store import PostgresStore

mem = Memory(store=PostgresStore("postgresql://user:pass@host/db"))
```

`PostgresStore` pools connections (`min_size`/`max_size`) and retries transient
connection, serialization, and deadlock errors with exponential backoff, so it
holds up under concurrent writers.

### Running the Postgres integration tests

The integration tests are skipped unless a database is reachable. To run them
locally with Docker:

```bash
pip install corticore[postgres]
# Docker running: a throwaway postgres:16-alpine container is managed for you
pytest tests/test_postgres_integration.py

# ...or point at an existing database instead of Docker:
CORTICORE_TEST_PG_DSN=postgresql://user:pass@host/db pytest tests/test_postgres_integration.py
```

## Schema migrations

The default SQLite store versions its schema with SQLite's built-in
`PRAGMA user_version` and applies any pending, ordered migrations
automatically when you open a store. Databases created by older corticore
releases are upgraded in place on connect with no data loss and no action
required from you. If a database reports a schema version newer than your
installed corticore build, the store refuses to open rather than risk
corrupting it — upgrade corticore in that case.

## Autonomous agent swarm

On top of the single research loop, corticore runs a small **swarm** of Cursor
agents (all **composer-2.5**) that operates every morning (04:00–09:00
Asia/Kolkata) and keeps the project healthy and release-ready. The primary
runtime is **local** (your laptop, via a systemd user timer); an optional
cloud path remains for CI smoke tests. See
[ADR 0006](research/design/adr/0006-agent-swarm-orchestration.md) and
[`deploy/systemd/README.md`](deploy/systemd/README.md).

How a daily local loop works:

- Parallel **thinker** agents scout for maintenance, research, and release-risk
  work and each propose bounded tasks.
- A read-only **judge** picks at most one proposal per cycle.
- A single **executor** - the only role allowed to write code - implements that
  scoped change as several small commits on a *dedicated* clone
  (`~/.local/share/corticore-swarm/checkout`). It never pushes.
- The orchestrator runs `pytest` + the eval gate; green HEAD is pushed to
  `origin/main`, red HEAD is hard-reset. Cycles repeat until the window closes
  or the soft daily commit ceiling (default 40) is hit. Quality over count —
  never pad.
- Every step is written to a durable ledger so interrupted work is *resumed*,
  not repeated.

### Release cadence (automatic, gated)

- **Friday** (local loop, end of window): bumps `pyproject.toml`, rolls
  `CHANGELOG.md` Unreleased → dated version, verifies, and pushes to `main`.
- That push triggers `.github/workflows/release.yml`, which publishes to PyPI
  via Trusted Publishing (OIDC) only when *every* gate clears:
  `RELEASE_ENABLED=true`, CI green, CHANGELOG entry present, no open
  `release-blocker` issues, no existing tag. Publishing is idempotent.

### Kill switches and cost controls

- `SWARM_ENABLED=true` (in `~/.config/corticore-swarm/env` for local, or the
  GitHub Actions variable for cloud) is required for the executor to write;
  otherwise the swarm only thinks.
- `RELEASE_ENABLED` (GitHub repo variable) must be `true` to publish.
- `orchestrate/swarm.yml` caps parallel thinkers, code-changing tasks per
  cycle, total runs, and the soft daily commit ceiling; `run_swarm.py` refuses
  to start work outside the operating window.

### Preview and local control

```bash
pip install -e ".[dev,orchestrate]"
python orchestrate/run_swarm.py --dry-run
python orchestrate/run_swarm.py --runtime local --no-write --ignore-window --skip-release
SWARM_ENABLED=true python orchestrate/run_swarm.py --runtime local --loop
./deploy/systemd/install.sh --enable   # schedule 04:00 Asia/Kolkata
```

### One-time activation (local)

1. Put `CURSOR_API_KEY` in the repo `.env` (or create a Cursor API key at
   [Dashboard → Integrations](https://cursor.com/dashboard/integrations)).
2. Run `./deploy/systemd/install.sh` once — it seeds the env file, enables
   user linger, and starts the 04:00 Asia/Kolkata timer. You do **not** need
   to start the swarm every day. If the laptop wakes after 09:00 with no run
   yet that day, `--catch-up` still does a bounded loop once.
3. Ensure SSH push access to `origin/main` from this machine.
4. For PyPI publish: set GitHub `RELEASE_ENABLED=true` and register this repo
   as a **PyPI Trusted Publisher**.

When there is no new paper/note ready, the research scout falls back to
studying peers in [`orchestrate/competitors.yml`](orchestrate/competitors.yml)
and proposing a small, ADR-compatible port.

### Incident recovery

- To stop everything immediately, set `SWARM_ENABLED=false` in the env file
  and/or `systemctl --user stop corticore-swarm.timer`.
- A failed local cycle never reaches `main` (verify-then-push). A failed
  release publish leaves no tag; fix forward and re-run — checks are idempotent.

## Project layout

```
src/corticore/     the library (core, stores, embeddings, dynamics, trace)
research/          paper -> note -> ADR trail behind every design decision
eval/              evaluation harness, BASELINE.md, and the regression gate
orchestrate/       paper-loop scripts + the agent swarm (swarm/, run_swarm.py)
examples/          runnable quickstart
tests/             unit tests
```

See [`research/design/DESIGN.md`](research/design/DESIGN.md) for the full
architecture and roadmap, and [`research/papers.yaml`](research/papers.yaml)
for the literature this project tracks and builds on.

## Status

v0.1 — SQLite backend (default), local embedder (default), decay/consolidate
/trace dynamics, time-bounded expiry. Optional extras: sentence-transformers
and Azure OpenAI embedders, Postgres backend. Scheduled paper-loop
orchestration is built and verified locally, pending activation (needs the
repo on GitHub + a `CURSOR_API_KEY` secret — see above). Additional backends
(Neo4j, Qdrant) and graph-structured/relational memory are tracked in the
roadmap — see [`research/design/DESIGN.md`](research/design/DESIGN.md) and
[`research/papers.yaml`](research/papers.yaml).

## License

MIT
