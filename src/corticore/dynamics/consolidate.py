"""Consolidation: `reflect()`'s dedup / merge / conflict-resolution / prune pass.

Human memory doesn't just accumulate — sleep consolidates it: near-duplicates
collapse, related memories merge, contradictions resolve in favor of the
more salient/recent version, and the unused fades. This module is the one
place all four of those behaviors live, so `Memory.reflect()` stays a thin
wrapper.

Conflict detection here is intentionally simple (lexical + embedding
similarity, not true semantic contradiction detection) — it is the first
thing to upgrade against papers in `research/papers.yaml` tagged
"experiential" / "evolution".
"""

from __future__ import annotations

import time

from corticore.core.config import Config
from corticore.core.types import ConsolidationReport, MemoryItem, MemoryStatus, TraceEvent
from corticore.dynamics.decay import decayed_salience
from corticore.dynamics.retrieval import keyword_score
from corticore.embeddings.base import Embedder
from corticore.embeddings.local import cosine_similarity
from corticore.stores.base import MemoryStore


def _similarity(a: MemoryItem, b: MemoryItem) -> float:
    kw = keyword_score(a.text, b.text)
    sim = cosine_similarity(a.embedding, b.embedding)
    return 0.5 * kw + 0.5 * sim


def _winner_loser(a: MemoryItem, b: MemoryItem) -> tuple[MemoryItem, MemoryItem]:
    """Higher salience wins; ties broken by recency."""
    if a.salience != b.salience:
        return (a, b) if a.salience > b.salience else (b, a)
    return (a, b) if a.created_at >= b.created_at else (b, a)


def reflect(
    store: MemoryStore,
    embedder: Embedder,  # reserved for v2 (re-embedding on merge, etc.)
    config: Config,
    now: float | None = None,
) -> ConsolidationReport:
    """Run one consolidation pass over all active memories."""
    now = now if now is not None else time.time()
    report = ConsolidationReport()

    active = [i for i in store.all() if i.status == MemoryStatus.ACTIVE]
    report.inspected = len(active)
    resolved: set[str] = set()

    for i in range(len(active)):
        a = active[i]
        if a.id in resolved:
            continue
        for j in range(i + 1, len(active)):
            b = active[j]
            if b.id in resolved:
                continue
            if a.namespace != b.namespace:
                continue  # never consolidate across namespace boundaries (F002)
            sim = _similarity(a, b)
            if sim < config.consolidation.merge_similarity_threshold:
                continue

            winner, loser = _winner_loser(a, b)
            is_duplicate = sim >= config.consolidation.duplicate_similarity_threshold

            loser.status = MemoryStatus.MERGED if is_duplicate else MemoryStatus.SUPERSEDED
            loser.superseded_by = winner.id
            store.put(loser)
            resolved.add(loser.id)

            kind = "merged" if is_duplicate else "superseded"
            detail = (
                f"{'duplicate of' if is_duplicate else 'superseded by'} "
                f"{winner.id} (similarity={sim:.3f})"
            )
            store.append_event(
                TraceEvent(
                    kind=kind,
                    at=now,
                    detail=detail,
                    data={"memory_id": loser.id, "winner_id": winner.id, "similarity": sim},
                )
            )
            if is_duplicate:
                report.merged.append((loser.id, winner.id))
            else:
                report.superseded.append((loser.id, winner.id))

            if loser.id == a.id:
                break  # `a` just lost; stop comparing it against the rest

    # Force-expire time-bounded ("Foresight", ADR 0003) memories first, since
    # this is independent of decay/salience and should not be masked by it.
    for item in store.all():
        if item.status != MemoryStatus.ACTIVE:
            continue
        if item.expires_at is not None and item.expires_at <= now:
            item.status = MemoryStatus.FORGOTTEN
            store.put(item)
            store.append_event(
                TraceEvent(
                    kind="expired",
                    at=now,
                    detail=f"expires_at {item.expires_at} <= now {now}",
                    data={"memory_id": item.id, "expires_at": item.expires_at},
                )
            )
            report.pruned.append(item.id)

    # Prune whatever is still active but has decayed below the forget threshold.
    for item in store.all():
        if item.status != MemoryStatus.ACTIVE:
            continue
        salience_now = decayed_salience(item, config.decay, now)
        if salience_now <= config.consolidation.forget_threshold:
            item.status = MemoryStatus.FORGOTTEN
            item.salience = salience_now
            store.put(item)
            store.append_event(
                TraceEvent(
                    kind="forgotten",
                    at=now,
                    detail=f"decayed salience {salience_now:.4f} <= threshold "
                    f"{config.consolidation.forget_threshold}",
                    data={"memory_id": item.id, "salience": salience_now},
                )
            )
            report.pruned.append(item.id)

    return report
