# ADR 0002: Forgetting is a first-class, always-on mechanism

## Status

Accepted (v0.1)

## Context

Across the surveyed field, memory systems are evaluated almost entirely on
retrieval quality; forgetting is either absent or an optional cleanup job.
Memoria (arXiv:2310.03052) frames this directly as the "fateful forgetting
problem" — systems that only ever accumulate eventually degrade retrieval
quality and cost, and lose the property that makes human memory useful:
what it drops matters as much as what it keeps. Hindsight
(arXiv:2512.12818) similarly frames retain/recall/reflect as a single loop,
not retrieval bolted onto storage.

Competitively, "we forget on purpose" is not a claim any of the
most-starred projects (Mem0, Letta, Zep, Cognee) lead with — it's an open
gap, and it's mechanically simple enough to implement without heavy
infrastructure, which keeps it compatible with ADR 0001's zero-setup
constraint.

## Decision

Every `MemoryItem` carries a `salience` that decays exponentially with time
since last access (`dynamics/decay.py`, half-life configurable via
`DecayConfig`, default one week). This decay is not an opt-in feature or a
background job the user has to schedule — it is applied:

1. **At recall time** — `dynamics/retrieval.py` multiplies the
   keyword+embedding relevance score by the current decay factor, so stale
   matches rank lower even before anything is pruned.
2. **At reflect time** — `dynamics/consolidate.py` hard-prunes (marks
   `FORGOTTEN`) any memory whose decayed salience drops at or below
   `ConsolidationConfig.forget_threshold`.

Consolidation additionally resolves near-duplicates and conflicting
memories by keeping the higher-salience (tie-broken by more recent) version
and marking the other `MERGED` or `SUPERSEDED` rather than leaving both
active — see `dynamics/consolidate.py::_winner_loser`.

## Consequences

- Decay and conflict resolution here use simple, legible heuristics
  (exponential half-life; lexical+embedding similarity thresholds), not a
  learned policy. ADR-relevant caution from the AgeMem paper note
  (`research/notes/2601.01885-agentic-memory.md`): memory-operation rewards
  are sparse and hard to attribute, which argues for keeping `reflect()`
  inspectable via `why()` rather than opaque, even as it gets smarter.
- `forget_threshold` and `half_life_seconds` are user-tunable per
  `Memory(config=...)`; a user who truly wants unbounded accumulation can
  set an effectively-infinite half-life, but that is not the default.
- Future upgrades to decay/consolidation (e.g. Nemori-style self-organizing
  memory, once reviewed) must land as replacements/extensions of these same
  `dynamics/*.py` functions, keeping the `Memory` facade unchanged.
