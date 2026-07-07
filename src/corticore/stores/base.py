"""Abstract storage interface — the seam v2 backends plug into.

Any backend (Postgres, Neo4j, Qdrant, ...) implements `MemoryStore` and can be
passed to `Memory(store=...)` without touching the public API, dynamics, or
trace modules. `sqlite_store.SQLiteStore` is the zero-setup default.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from corticore.core.types import MemoryItem, TraceEvent


class MemoryStore(ABC):
    """Persistence + lookup contract for memory items and their trace events."""

    @abstractmethod
    def put(self, item: MemoryItem) -> None:
        """Insert or update a memory item."""

    @abstractmethod
    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """Fetch a single memory item by id, or None if it doesn't exist."""

    @abstractmethod
    def delete(self, memory_id: str) -> None:
        """Hard-delete a memory item."""

    @abstractmethod
    def all(self) -> list[MemoryItem]:
        """Return every memory item currently stored (any status)."""

    @abstractmethod
    def append_event(self, event: TraceEvent) -> None:
        """Record a trace event against a memory id."""

    @abstractmethod
    def events_for(self, memory_id: str) -> list[TraceEvent]:
        """Return all trace events recorded for a memory id, in order."""

    @abstractmethod
    def close(self) -> None:
        """Release any underlying resources (connections, file handles)."""

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
