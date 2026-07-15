"""Tests for the ledger backends and resumability logic."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.ledger import (  # noqa: E402
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    FileLedger,
    InMemoryLedger,
    LedgerEntry,
    find_resumable,
)


def _entry(task, role, status, agent_id=None):
    return LedgerEntry(
        cycle_id="c1",
        task=task,
        role=role,
        status=status,
        summary="s",
        agent_id=agent_id,
    )


def test_in_memory_round_trip():
    ledger = InMemoryLedger()
    ledger.record(_entry("t", "scout", STATUS_COMPLETED))
    assert len(ledger.entries()) == 1
    assert ledger.entries()[0].role == "scout"


def test_file_ledger_round_trip(tmp_path):
    ledger = FileLedger(tmp_path / "sub" / "ledger.jsonl")
    ledger.record(_entry("t", "scout", STATUS_COMPLETED, agent_id="bc-1"))
    ledger.record(_entry("t", "executor", STATUS_IN_PROGRESS, agent_id="bc-2"))
    reloaded = FileLedger(tmp_path / "sub" / "ledger.jsonl")
    entries = reloaded.entries()
    assert [e.role for e in entries] == ["scout", "executor"]
    assert entries[1].agent_id == "bc-2"


def test_find_resumable_returns_in_progress_with_agent():
    ledger = InMemoryLedger()
    ledger.record(_entry("t", "executor", STATUS_IN_PROGRESS, agent_id="bc-9"))
    resumable = find_resumable(ledger, "t")
    assert resumable is not None
    assert resumable.agent_id == "bc-9"


def test_find_resumable_none_when_completed_after():
    ledger = InMemoryLedger()
    ledger.record(_entry("t", "executor", STATUS_IN_PROGRESS, agent_id="bc-9"))
    ledger.record(_entry("t", "executor", STATUS_COMPLETED, agent_id="bc-9"))
    assert find_resumable(ledger, "t") is None


def test_find_resumable_ignores_other_tasks():
    ledger = InMemoryLedger()
    ledger.record(_entry("other", "executor", STATUS_IN_PROGRESS, agent_id="bc-9"))
    assert find_resumable(ledger, "t") is None


def test_find_resumable_requires_agent_id():
    ledger = InMemoryLedger()
    ledger.record(_entry("t", "executor", STATUS_IN_PROGRESS, agent_id=None))
    assert find_resumable(ledger, "t") is None
