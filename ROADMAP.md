# Roadmap

This roadmap is driven by `feature-list.csv`, not the other way around.
That file is a local, agent-only backlog sheet (gitignored, not published in
this repo) that tracks each feature's status, competitor reference, vision
fit, and test plan. See
[`.cursor/skills/corticore-feature-builder/SKILL.md`](.cursor/skills/corticore-feature-builder/SKILL.md)
for the workflow agents follow to move a row from idea to done.

Corticore's north star stays fixed while these features are built: a
local-first, forgetting-first, fully-inspectable memory layer that other
agent frameworks can depend on — not a hosted platform, not a graph
database, and not a full agent runtime.

## Near-term (accepted)

1. **Metadata-filtered recall** (`F001`) — scope `recall()` by metadata
   (e.g. `user_id`, `tags`) before scoring. Prerequisite for multi-tenant use.
2. **Namespaced memories** (`F002`) — isolate memories per user/session/agent
   while keeping the single-tenant default unchanged.
3. **SQLite schema migrations** (`F003`) — versioned schema upgrades so the
   store can evolve safely; unblocks `F001`, `F002`, `F006`.

## Researching

4. **Semantic embedder benchmark** (`F004`) — quantify the
   `sentence-transformers` vs. `LocalEmbedder` gap already flagged in
   [`eval/BASELINE.md`](eval/BASELINE.md).
5. **Async memory API** (`F005`) — `aremember`/`arecall`/`areflect` for async
   agent runtimes, sync API stays the default.

## Ideas (not yet scoped)

6. **JSONL import/export** (`F006`) — backup/restore/debugging.
7. **Structured memory types** (`F007`) — optional `semantic`/`episodic`/
   `procedural` tagging, queryable via `F001`.
8. **Observability hooks** (`F008`) — optional structured logging callback
   for production monitoring.
9. **Postgres store hardening** (`F009`) — pooling, retries, integration
   tests for the existing optional `PostgresStore`.
10. **CLI inspection tool** (`F010`) — `corticore recall|why|reflect` against
    a local `.db` file, in keeping with the local-first, file-based model.

## Explicitly rejected for v1

- **Knowledge-graph backend** (`F011`) — conflicts with the "no graph
  database by default" promise; revisit only as an optional backend if a
  specific paper in `research/papers.yaml` justifies it.
- **Full agent runtime / self-editing agents** (`F012`) — out of scope;
  corticore is a memory layer that frameworks like LangGraph or custom
  agents depend on, not a competing agent runtime like Letta.

## Process

Every feature above must be researched against its competitor reference,
re-checked against corticore's vision, implemented behind existing
abstractions, tested (`pytest` + `eval/harness.py`), and tracked back into
`feature-list.csv` before it is considered done.
