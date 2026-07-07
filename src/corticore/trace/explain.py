"""`why()`: turn a memory's stored history into a human-readable explanation.

This is the third differentiator (alongside forgetting and conflict
resolution): every decision a memory has been through — stored, recalled,
merged, superseded, forgotten — is logged as a `TraceEvent` by the module
that made the decision, and this module just assembles them into a `Trace`.
"""

from __future__ import annotations

from corticore.core.config import Config
from corticore.core.types import Trace
from corticore.dynamics.decay import decay_factor
from corticore.stores.base import MemoryStore


class MemoryNotFoundError(KeyError):
    """Raised by `why()` when the given memory id doesn't exist."""


def explain(
    store: MemoryStore,
    config: Config,
    memory_id: str,
    now: float | None = None,
) -> Trace:
    """Build the full explanation trace for a single memory."""
    item = store.get(memory_id)
    if item is None:
        raise MemoryNotFoundError(f"no memory with id {memory_id!r}")

    events = store.events_for(memory_id)
    factor = decay_factor(item, config.decay, now)

    return Trace(
        memory_id=item.id,
        text=item.text,
        status=item.status,
        salience=item.salience,
        decay_factor=factor,
        events=events,
    )
