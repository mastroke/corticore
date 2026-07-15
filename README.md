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

## Schema migrations

The default SQLite store versions its schema with SQLite's built-in
`PRAGMA user_version` and applies any pending, ordered migrations
automatically when you open a store. Databases created by older corticore
releases are upgraded in place on connect with no data loss and no action
required from you. If a database reports a schema version newer than your
installed corticore build, the store refuses to open rather than risk
corrupting it — upgrade corticore in that case.

## Project layout

```
src/corticore/     the library (core, stores, embeddings, dynamics, trace)
research/          paper -> note -> ADR trail behind every design decision
eval/              reproducible evaluation harness, results, and BASELINE.md
orchestrate/       scheduled paper-loop scripts + prompt (see ADR 0005)
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
