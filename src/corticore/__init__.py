"""corticore: a zero-setup, forgetting-first, fully-inspectable memory layer for AI agents."""

from corticore.core.memory import Memory
from corticore.core.types import (
    ConsolidationReport,
    MemoryItem,
    MemoryStatus,
    MemoryType,
    RecallResult,
    Trace,
    TraceEvent,
)

__version__ = "0.1.0"

__all__ = [
    "Memory",
    "MemoryItem",
    "MemoryStatus",
    "MemoryType",
    "RecallResult",
    "ConsolidationReport",
    "Trace",
    "TraceEvent",
    "__version__",
]
