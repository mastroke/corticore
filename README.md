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
cloud agents that operates every morning (04:00-09:00 Asia/Kolkata) and keeps
the project healthy and release-ready. See
[ADR 0006](research/design/adr/0006-agent-swarm-orchestration.md) for the full
reasoning; the code is under `orchestrate/swarm/` and `orchestrate/run_swarm.py`.

How a daily cycle works:

- Parallel **thinker** agents (GPT-class reasoning) scout for maintenance,
  research, and release-risk work and each propose bounded tasks.
- A read-only **judge** picks at most one proposal for the day.
- A single **executor** (Composer) - the only role allowed to write code -
  implements that one scoped change and opens one PR. It never pushes to `main`.
- Every step is written to a durable ledger so interrupted work is *resumed*,
  not repeated.

Separately, a **weekend verifier** re-checks the week's merged `main` from a
clean clone with no planner context (tests + eval gate + clean-room wheel
import) and files a `release-blocker` issue if anything fails.

### Release cadence (automatic, gated)

- **Thursday** (`release-prep.yml`) computes the semantic bump deterministically
  from merged change labels (`breaking`→major, `feature`→minor, `fix`→patch),
  rolls `CHANGELOG.md`, and opens an auto-merge `Release <version>` PR.
- **Friday** (`release.yml`) publishes only when *every* gate clears: kill
  switch on, CI green, verifier green, CHANGELOG entry present, clean history,
  no open `release-blocker` issues, no existing tag, and PyPI Trusted
  Publishing configured. Publishing uses OIDC (no API token) and is idempotent.

### Kill switches and cost controls

- `SWARM_ENABLED` (repo variable) must be `true` for the executor to write
  anything; otherwise the swarm only thinks.
- `RELEASE_ENABLED` (repo variable) must be `true` to publish.
- `orchestrate/swarm.yml` caps parallel thinkers, code-changing tasks per cycle
  (default 1), and total runs; `run_swarm.py` refuses to start work outside the
  operating window and enforces a per-cycle deadline.

### Preview and manual control

```bash
pip install -e ".[dev,orchestrate]"
python orchestrate/run_swarm.py --dry-run        # print every prompt, no API key, no agents
python orchestrate/run_swarm.py --no-write       # run thinkers/judge for real, never the executor
python orchestrate/prepare_release.py --dry-run  # show the computed version bump only
```

Each workflow also has a `workflow_dispatch` trigger for manual, on-demand runs.

### One-time activation

The swarm can only be switched on with a few external, one-time steps (not
doable from a code checkout):

1. Enable **Long running agents** for your Cursor team (Team Settings) and
   create a least-privilege **service-account** API key with access to the repo.
2. Add secrets/variables in GitHub (Settings → Secrets and variables → Actions):
   `CURSOR_API_KEY` (secret); `SWARM_ENABLED`, `RELEASE_ENABLED` (variables);
   optionally `SWARM_LEDGER_ISSUE` (a tracking issue number for the ledger).
3. Configure branch protection on `main` requiring the **CI** and **Weekend
   verifier** checks, and enable auto-merge for the release PR.
4. Register this repo's release workflow as a **PyPI Trusted Publisher**
   (there is no `corticore` project on PyPI yet, so do this before the first
   unattended publish).

### Incident recovery

- To stop everything immediately, set `SWARM_ENABLED` and `RELEASE_ENABLED` to
  `false` - in-flight runs finish, no new work starts, and nothing publishes.
- A failed release leaves no tag (the tag is created only on the publish path);
  fix forward and let the next cycle re-run - `skip-existing` and the tag/version
  checks make re-runs idempotent.
- Resolve any open `release-blocker` issue before re-enabling releases.

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
