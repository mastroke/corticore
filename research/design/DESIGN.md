# corticore — design

## Positioning

The agent-memory space is crowded and well-funded (Mem0 ~60k stars, Letta
~24k, Zep/Graphiti ~24k, Cognee ~12k — see the comparison sources cited in
the project's founding discussion). Every one of them requires standing up
infrastructure — a graph database, a vector database, a running server —
before you write application code. None of them treats **forgetting** as a
first-class, inspectable mechanism; they retrieve well and accumulate
forever.

corticore's bet: **own the zero-setup tier, and lead with forgetting +
inspectability instead of "more storage."**

corticore does **not** claim to replicate "every feature of the human
brain." That framing doesn't survive contact with a reviewer or a
competitor, and it isn't buildable. What's buildable and defensible is a
narrow, well-scoped slice of human memory's most useful properties:
memories fade if unused, contradictions get reconciled instead of piling
up, and the system can explain itself. See `research/taxonomy.md` for how
this maps onto the field's own taxonomy.

## Architecture

```
Memory (core/memory.py)          <- thin public API, no logic of its own
  |-- MemoryStore (stores/base.py)      <- v2 seam: swap SQLite for Postgres/Neo4j/Qdrant
  |     `-- SQLiteStore (default)
  |-- Embedder (embeddings/base.py)     <- v2 seam: swap local hashing for sentence-transformers/OpenAI
  |     `-- LocalEmbedder (default, zero dependencies)
  |-- dynamics/
  |     |-- decay.py         (forgetting: exponential half-life salience)
  |     |-- retrieval.py     (hybrid keyword+embedding, decay-adjusted ranking)
  |     `-- consolidate.py   (reflect(): dedup / merge / conflict resolution / prune)
  `-- trace/
        `-- explain.py       (why(): assembles TraceEvents into a Trace)
```

Every dynamics module is a pure function over `(items, config, ...)` plus a
`MemoryStore`/`Embedder` it's handed — none of them import each other's
private internals, and none of them know which store or embedder backend is
in play. That's what makes v2 additive rather than a rewrite:

- A new backend implements `stores/base.py::MemoryStore` and nothing else in
  the codebase changes.
- A new embedding model implements `embeddings/base.py::Embedder`.
- A smarter decay curve, a real contradiction detector, or graph-based
  retrieval is a new function passed into (or replacing) the corresponding
  `dynamics/*.py` module, gated by a paper + ADR (see below).

## Why every decision must trace to a paper + ADR

This project reads its way through
[Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
starting from January 2026. To keep that research effort from turning into
scope creep or unfalsifiable claims, the rule is:

> Nothing gets implemented without a `research/papers.yaml` entry, a
> distilled note in `research/notes/`, and — if it changes the codebase — an
> ADR in `research/design/adr/` that the code links back to.

This also means v2 planning is just: read `papers.yaml`, find `unreviewed`
entries, write notes, decide adopt/defer/reject, and only the "adopt" ones
turn into ADRs and code.

## v0.1 scope (this build)

- SQLite store (default), local zero-dependency embedder (default).
- `remember` / `recall` / `reflect` / `why` — the whole public API.
- Decay-based forgetting, similarity-based dedup/merge/conflict resolution,
  time-bounded expiry (ADR 0003), full trace history.
- Synthetic eval harness (real benchmark datasets are v2).

## Depth round (research + optional extras)

All 5 Jan-2026 papers tracked in `papers.yaml` have now been reviewed:

- **Adopted:** EverMemOS's "Foresight" time-bounded expiry (ADR 0003) — the
  only idea across this batch that was both genuinely new to corticore and
  cheap enough to fit the zero-setup constraint.
- **Deferred, with validated existing design:** MAGMA's dual-stream
  ingest/consolidation pattern and EverMemOS's MemCell→MemScene
  consolidation both independently validate corticore's existing
  `remember()`/`reflect()` split — no code changed as a result, but it's
  useful confirmation the architecture is on the right track.
- **Deferred, real future work:** MemRL's learned-utility retrieval (needs
  RL infra), CompassMem's Event Graph and MAGMA's multi-graph retrieval
  (both need relational/graph storage) — see their notes in
  `research/notes/` for what a cheap first step toward each might look like.

Also added, as opt-in extras behind the existing `stores/base.py` and
`embeddings/base.py` seams (none of these change the zero-setup default):

- `embeddings/sentence_transformer.py` — local semantic embeddings (`[st]`).
- `embeddings/azure_openai.py` — Azure OpenAI embeddings (`[openai]`),
  credentials via environment variables only, never hardcoded.
- `stores/postgres_store.py` — multi-writer/production backend (`[postgres]`),
  schema-identical to `SQLiteStore` including `expires_at`.

See ADR 0003 (Foresight), ADR 0004 (Postgres) for the reasoning behind each.

## Orchestration round (paper-loop automation)

The manual paper -> note -> decision -> code -> PR loop run by hand across
the v0.1 and depth rounds is now automated, configured, and pending
activation:

- `.github/workflows/paper-loop.yml` — weekly cron + manual dispatch.
- `orchestrate/check_new_papers.py` — pure-function paper-list diff against
  `research/papers.yaml` (verified against the live list: 0 new papers, as
  expected — every currently-listed 2026-01+ paper is already tracked).
- `orchestrate/run_cloud_agent.py` — launches a Cursor cloud agent via the
  Python SDK's `Agent.prompt(..., cloud=...)` only when new papers are
  found; `--dry-run` prints the exact prompt without an API call.
- `orchestrate/prompts/paper_loop_instructions.md` — the versioned playbook,
  codifying exactly the process used by hand in prior rounds.
- `eval/BASELINE.md` — the committed regression baseline every automated run
  must check itself against before opening a PR.

See [ADR 0005](adr/0005-scheduled-cloud-agent-research-loop.md) for the full
reasoning, including why activation (pushing to GitHub, adding the
`CURSOR_API_KEY` secret, granting repo access) is a manual step outside this
repo's code.

## Explicitly deferred to v2

- Additional store backends beyond Postgres (Neo4j, Qdrant).
- Graph-structured/relational factual memory (CompassMem, MAGMA).
- Experiential/procedural memory and learned-utility retrieval (MemRL).
- Real benchmark datasets (LoCoMo, LongMemEval) in the eval harness.
