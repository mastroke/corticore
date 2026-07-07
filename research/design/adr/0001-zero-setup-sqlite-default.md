# ADR 0001: Zero-setup SQLite + local embedder as the default backend

## Status

Accepted (v0.1)

## Context

Every widely-adopted agent-memory library requires external infrastructure
before first use: Zep/Graphiti needs a graph database, Letta runs an
agent-hosting server, Cognee needs both a graph store and a vector store.
Mem0 (arXiv:2504.19413) is the closest to easy setup and is the most-starred
project in the category (~60k stars), largely on the strength of a fast
time-to-first-`remember()`.

Our positioning (see `research/design/DESIGN.md`) is explicitly to own the
"bare-minimum setup" tier of this market. That's a hard requirement, not a
nice-to-have — if `pip install corticore` needs a running database, we've
lost the differentiator before any code runs.

## Decision

The default `MemoryStore` is `stores/sqlite_store.SQLiteStore` (a single
file, standard library `sqlite3`, no server). The default `Embedder` is
`embeddings/local.LocalEmbedder` (a deterministic hashed bag-of-words, no
model download, no API key, no third-party dependency).

Both are hidden behind abstract interfaces (`stores/base.py`,
`embeddings/base.py`) specifically so this decision is reversible per-user
without being reversible for the project: anyone can pass
`Memory(store=PostgresStore(...), embedder=OpenAIEmbedder(...))` once those
exist, but `Memory("agent.db")` must always work standalone.

## Consequences

- `LocalEmbedder` captures lexical overlap, not semantic meaning — it will
  under-perform a real embedding model on paraphrase-heavy recall. This is
  an accepted, documented tradeoff for v0.1 (see the README's Status
  section); `[st]`/`[openai]` extras are reserved in `pyproject.toml` for
  when real embedder classes are added.
- SQLite is single-writer; fine for the target use case (a single agent's
  local memory), not intended for high-concurrency multi-agent shared
  memory. That use case is explicitly deferred to a v2 backend, not solved
  by stretching SQLite.
