"""The public API: `Memory.remember / recall / reflect / why`.

This facade is intentionally thin — it wires together a `MemoryStore`, an
`Embedder`, and the `dynamics`/`trace` modules, but contains no algorithmic
logic itself. That logic lives in `dynamics/` and `trace/` precisely so it
can be swapped or extended (v2 backends, smarter decay, richer conflict
detection) without changing this class's surface.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Optional

from corticore.core.config import Config
from corticore.core.types import (
    MEMORY_TYPE_KEY,
    ConsolidationReport,
    MemoryItem,
    MemoryStatus,
    MemoryType,
    RecallResult,
    Trace,
    TraceEvent,
)


def _item_to_dict(item: MemoryItem) -> dict[str, Any]:
    """Serialize a MemoryItem to a JSON-safe dict (status enum -> its value)."""
    return {
        "id": item.id,
        "text": item.text,
        "namespace": item.namespace,
        "metadata": item.metadata,
        "embedding": item.embedding,
        "created_at": item.created_at,
        "last_accessed_at": item.last_accessed_at,
        "access_count": item.access_count,
        "salience": item.salience,
        "status": item.status.value,
        "superseded_by": item.superseded_by,
        "expires_at": item.expires_at,
    }


def _item_from_dict(data: dict[str, Any]) -> MemoryItem:
    """Rebuild a MemoryItem from a dict produced by `_item_to_dict`."""
    return MemoryItem(
        id=data["id"],
        text=data["text"],
        namespace=data.get("namespace", "default"),
        metadata=data.get("metadata", {}),
        embedding=data.get("embedding", []),
        created_at=data["created_at"],
        last_accessed_at=data["last_accessed_at"],
        access_count=data.get("access_count", 0),
        salience=data.get("salience", 1.0),
        status=MemoryStatus(data.get("status", "active")),
        superseded_by=data.get("superseded_by"),
        expires_at=data.get("expires_at"),
    )
from corticore.dynamics import consolidate as consolidate_mod
from corticore.dynamics.decay import boost_on_access
from corticore.dynamics.retrieval import retrieve
from corticore.embeddings.base import Embedder
from corticore.embeddings.local import LocalEmbedder
from corticore.stores.base import MemoryStore
from corticore.stores.sqlite_store import SQLiteStore
from corticore.trace.explain import explain


class Memory:
    """Zero-setup, forgetting-first, inspectable memory for AI agents.

    >>> mem = Memory("agent.db")
    >>> mem.remember("The user's name is Priya.")
    >>> mem.recall("what is the user's name?")
    """

    def __init__(
        self,
        path: str = "corticore.db",
        store: Optional[MemoryStore] = None,
        embedder: Optional[Embedder] = None,
        config: Optional[Config] = None,
    ) -> None:
        self.config = config or Config()
        self.store: MemoryStore = store or SQLiteStore(path)
        self.embedder: Embedder = embedder or LocalEmbedder()

    def remember(
        self,
        text: str,
        metadata: Optional[dict[str, Any]] = None,
        expires_at: Optional[float] = None,
        namespace: str = "default",
        memory_type: Optional[str] = None,
    ) -> str:
        """Store a new memory and return its id.

        `expires_at` is an optional epoch-seconds deadline (EverMemOS-style
        "Foresight" signal, see ADR 0003): once passed, `reflect()` forgets
        this memory regardless of how recently or often it's been recalled.

        `namespace` isolates this memory to a logical partition (e.g. a user
        or agent id). Memories in different namespaces never surface in each
        other's `recall()` results. Defaults to `"default"`.

        `memory_type` optionally tags the memory's cognitive category (see
        `MemoryType`: semantic/episodic/procedural). It is stored under
        `metadata["memory_type"]`, so it is filterable via
        `recall(filters={"memory_type": ...})`.
        """
        now = time.time()
        memory_id = uuid.uuid4().hex
        metadata = dict(metadata or {})
        if memory_type is not None:
            metadata[MEMORY_TYPE_KEY] = (
                memory_type.value if isinstance(memory_type, MemoryType) else memory_type
            )
        item = MemoryItem(
            id=memory_id,
            text=text,
            namespace=namespace,
            metadata=metadata,
            embedding=self.embedder.embed(text),
            created_at=now,
            last_accessed_at=now,
            salience=1.0,
            expires_at=expires_at,
        )
        self.store.put(item)
        self.store.append_event(
            TraceEvent(
                kind="stored",
                at=now,
                detail=f"remembered: {text!r}",
                data={"memory_id": memory_id},
            )
        )
        return memory_id

    def recall(
        self,
        query: str,
        k: Optional[int] = None,
        filters: Optional[dict[str, Any]] = None,
        namespace: Optional[str] = "default",
    ) -> list[RecallResult]:
        """Return the `k` most relevant, decay-adjusted memories for `query`.

        `filters` narrows candidates to memories whose `metadata` matches
        every key/value pair exactly (e.g. `{"user_id": "abc"}`), applied
        before scoring.

        `namespace` scopes the search to a single logical partition and
        defaults to `"default"` (the implicit namespace for memories stored
        without one). Pass `namespace=None` to search across all namespaces.
        """
        now = time.time()
        items = self.store.all()
        results = retrieve(
            query,
            items,
            self.embedder,
            self.config,
            k=k,
            now=now,
            filters=filters,
            namespace=namespace,
        )

        for result in results:
            item = self.store.get(result.id)
            if item is None:
                continue
            boost_on_access(item, self.config.decay, now)
            self.store.put(item)
            self.store.append_event(
                TraceEvent(
                    kind="recalled",
                    at=now,
                    detail=f"recalled for query {query!r} (score={result.score:.3f})",
                    data={"memory_id": item.id, "query": query, "score": result.score},
                )
            )
        return results

    def reflect(self) -> ConsolidationReport:
        """Run one consolidation pass: dedup, merge, resolve conflicts, prune."""
        return consolidate_mod.reflect(self.store, self.embedder, self.config)

    def why(self, memory_id: str) -> Trace:
        """Explain the full history behind a memory."""
        return explain(self.store, self.config, memory_id)

    async def aremember(self, *args: Any, **kwargs: Any) -> str:
        """Async `remember`: runs the blocking store write in a worker thread.

        For use inside async agent runtimes so a memory write does not block
        the event loop. The sync `remember` remains the primary API.
        """
        return await asyncio.to_thread(self.remember, *args, **kwargs)

    def export_jsonl(self, path: str) -> int:
        """Write every stored memory to `path` as JSON Lines; return the count.

        One memory per line, so exports stream and diff cleanly. Useful for
        backup, migration between stores, and debugging.
        """
        items = self.store.all()
        with open(path, "w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(_item_to_dict(item), ensure_ascii=False) + "\n")
        return len(items)

    def import_jsonl(self, path: str) -> int:
        """Load memories from a JSON Lines `path` into this store; return count.

        Each line is a memory produced by `export_jsonl`. Existing memories
        with the same id are overwritten (the store's `put` is an upsert), so
        re-importing is idempotent. Blank lines are ignored.
        """
        count = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                self.store.put(_item_from_dict(json.loads(line)))
                count += 1
        return count

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
