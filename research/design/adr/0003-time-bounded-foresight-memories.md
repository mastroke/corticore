# ADR 0003: Time-bounded ("Foresight") memory expiry

## Status

Accepted (v0.1, depth round)

## Context

EverMemOS (arXiv:2601.02163) introduces "Foresight" signals as part of its
Episodic Trace Formation stage: facts that carry a known future relevance
window (e.g. "the meeting is next Friday," "the promo code expires at
midnight") rather than only a past timestamp. corticore's forgetting
mechanism (ADR 0002) is entirely access-based decay — a fact fades only if
it stops being recalled. That leaves a real gap: a fact can be *wrong to
keep recalling* even while it's still being actively accessed, because its
relevance has a hard deadline unrelated to access frequency.

This is a rare case in the current paper-review batch: an idea that is
directly reusable with zero new infrastructure, fits the zero-setup
constraint (ADR 0001) exactly, and strengthens corticore's core
differentiator (forgetting on purpose) rather than adding a new axis of
complexity.

## Decision

`MemoryItem` gains an optional `expires_at: float | None` field (epoch
seconds). `Memory.remember(text, metadata=None, expires_at=None)` exposes
it directly. During `reflect()` (`dynamics/consolidate.py`), any `ACTIVE`
memory whose `expires_at` has passed is force-marked `FORGOTTEN` — before
the decay-based prune pass runs, so it is not masked by a high salience
score. This is logged as its own `TraceEvent` kind (`"expired"`), distinct
from `"forgotten"` (decay-based), so `why()` can tell the two apart.

Expiry is strictly additive: memories without `expires_at` set (the
default, `None`) are completely unaffected and behave exactly as before
this ADR.

## Consequences

- corticore now has two independent forgetting triggers: access-based decay
  (ADR 0002) and time-bounded expiry (this ADR). They compose — an expired
  memory is forgotten even if frequently accessed, and a never-expiring,
  rarely-accessed memory still decays as before.
- `expires_at` is a plain field on every store (SQLite now, Postgres — ADR
  0004 — from day one), so no store-specific migration path is needed for
  backends added after this ADR.
- This does not adopt EverMemOS's `MemCell`/`MemScene` structures or its
  `Reconstructive Recollection` retrieval stage — only the narrow, cheap
  "time-bounded fact" idea. The rest of EverMemOS is noted as validating
  corticore's existing consolidation design (see
  `research/notes/2601.02163-evermemos.md`), not adopted as new code.
