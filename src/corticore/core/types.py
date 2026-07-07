"""Core data types shared across corticore.

These types are the contract between the public API (`core.memory.Memory`)
and every pluggable component (stores, embeddings, dynamics, trace). Keeping
them here — independent of any specific backend — is what lets v2 add new
stores or algorithms without changing the shapes callers depend on.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MemoryStatus(str, Enum):
    """Lifecycle state of a stored memory."""

    ACTIVE = "active"
    MERGED = "merged"
    SUPERSEDED = "superseded"
    FORGOTTEN = "forgotten"


@dataclass
class MemoryItem:
    """A single unit of stored memory."""

    id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    salience: float = 1.0
    status: MemoryStatus = MemoryStatus.ACTIVE
    superseded_by: Optional[str] = None
    expires_at: Optional[float] = None
    """Optional epoch-seconds deadline (EverMemOS-style "Foresight" signal).

    Independent of access-based decay: a memory with `expires_at` set is
    force-forgotten by `reflect()` once that time passes, regardless of how
    recently or often it was recalled. See ADR 0003.
    """


@dataclass
class RecallResult:
    """A memory returned from `recall()`, ranked by decay-adjusted relevance."""

    id: str
    text: str
    metadata: dict[str, Any]
    score: float
    similarity: float
    decay_factor: float
    created_at: float


@dataclass
class TraceEvent:
    """One step in a memory's life, used to build `why()` explanations."""

    kind: str  # e.g. "stored", "decayed", "merged", "superseded", "recalled"
    at: float
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    """Full explanation of why a memory looks the way it does."""

    memory_id: str
    text: str
    status: MemoryStatus
    salience: float
    decay_factor: float
    events: list[TraceEvent] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - human-readable convenience
        lines = [
            f"Memory {self.memory_id} [{self.status.value}]",
            f"  text: {self.text!r}",
            f"  salience={self.salience:.3f} decay_factor={self.decay_factor:.3f}",
            "  history:",
        ]
        for ev in self.events:
            lines.append(f"    - {ev.kind}: {ev.detail}")
        return "\n".join(lines)


@dataclass
class ConsolidationReport:
    """Summary of what a `reflect()` pass did."""

    merged: list[tuple[str, str]] = field(default_factory=list)  # (loser, winner)
    superseded: list[tuple[str, str]] = field(default_factory=list)  # (old, new)
    pruned: list[str] = field(default_factory=list)
    inspected: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.merged or self.superseded or self.pruned)
