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


def _resolve_version() -> str:
    """Single source of truth for the version is `pyproject.toml`.

    When corticore is installed, the built package metadata carries the
    version, so we read it via importlib.metadata rather than duplicating the
    literal here (a duplicate is exactly the kind of drift the release
    pipeline's consistency test guards against). Falling back to reading
    pyproject.toml keeps `__version__` correct when running from a source
    checkout that hasn't been installed.
    """
    try:
        from importlib.metadata import version

        return version("corticore")
    except Exception:  # noqa: BLE001 - fall back for uninstalled source trees
        pass

    try:
        from pathlib import Path

        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        for line in pyproject.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("version"):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        pass

    return "0.0.0+unknown"


__version__ = _resolve_version()

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
