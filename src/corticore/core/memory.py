"""The public API: `Memory.remember / recall / reflect / why`.

This facade is intentionally thin — it wires together a `MemoryStore`, an
`Embedder`, and the `dynamics`/`trace` modules, but contains no algorithmic
logic itself. That logic lives in `dynamics/` and `trace/` precisely so it
can be swapped or extended (v2 backends, smarter decay, richer conflict
detection) without changing this class's surface.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from corticore.core.config import Config
from corticore.core.types import ConsolidationReport, MemoryItem, RecallResult, Trace, TraceEvent
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
    ) -> str:
        """Store a new memory and return its id.

        `expires_at` is an optional epoch-seconds deadline (EverMemOS-style
        "Foresight" signal, see ADR 0003): once passed, `reflect()` forgets
        this memory regardless of how recently or often it's been recalled.

        `namespace` isolates this memory to a logical partition (e.g. a user
        or agent id). Memories in different namespaces never surface in each
        other's `recall()` results. Defaults to `"default"`.
        """
        now = time.time()
        memory_id = uuid.uuid4().hex
        item = MemoryItem(
            id=memory_id,
            text=text,
            namespace=namespace,
            metadata=metadata or {},
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
    ) -> list[RecallResult]:
        """Return the `k` most relevant, decay-adjusted memories for `query`.

        `filters` narrows candidates to memories whose `metadata` matches
        every key/value pair exactly (e.g. `{"user_id": "abc"}`), applied
        before scoring. Omitting it searches across all memories, matching
        prior behavior exactly.
        """
        now = time.time()
        items = self.store.all()
        results = retrieve(query, items, self.embedder, self.config, k=k, now=now, filters=filters)

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

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
