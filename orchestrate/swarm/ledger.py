"""Durable run ledger: append-only record of what the swarm did and where.

Long-running and cross-day work needs state that survives a workflow run
ending. Rather than a database, the ledger is an append-only log of small
JSON entries. Two production-facing backends are provided plus an in-memory
one for tests, all behind the same `Ledger` protocol:

- `InMemoryLedger` - tests and dry runs.
- `FileLedger` - a local JSONL file (useful for a self-hosted scheduler).
- `GitHubLedger` - mirrors entries as comments on a tracking GitHub issue via
  the `gh` CLI, so the audit trail lives next to the code it changed.

Entries are the seam that makes work resumable: an interrupted task can be
found by its `task` + `status == "in_progress"` and continued via the agent
id recorded on the entry, instead of being launched again from scratch.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol

# Lifecycle statuses an entry can carry.
STATUS_STARTED = "started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_BLOCKED = "blocked"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class LedgerEntry:
    """One immutable event in the swarm's history."""

    cycle_id: str
    task: str
    role: str
    status: str
    summary: str
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    detail: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=_utcnow_iso)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @staticmethod
    def from_json(text: str) -> "LedgerEntry":
        data = json.loads(text)
        return LedgerEntry(**data)


class Ledger(Protocol):
    def record(self, entry: LedgerEntry) -> None: ...

    def entries(self) -> List[LedgerEntry]: ...


def find_resumable(ledger: Ledger, task: str) -> Optional[LedgerEntry]:
    """Return the newest in-progress entry for `task` that carries an agent id.

    "Resumable" means an agent was launched, the run didn't reach a terminal
    status, and we know which agent to resume. Terminal entries (completed,
    failed, cancelled) for the same task after the in-progress one cancel it
    out - the work already concluded.
    """
    latest: Optional[LedgerEntry] = None
    for entry in ledger.entries():
        if entry.task != task:
            continue
        if entry.status == STATUS_IN_PROGRESS and entry.agent_id:
            latest = entry
        elif entry.status in (
            STATUS_COMPLETED,
            STATUS_FAILED,
            STATUS_CANCELLED,
        ):
            # A later terminal status supersedes an earlier in-progress one.
            if latest and entry.agent_id == latest.agent_id:
                latest = None
    return latest


class InMemoryLedger:
    """A ledger that lives only for the process. For tests and dry runs."""

    def __init__(self) -> None:
        self._entries: List[LedgerEntry] = []

    def record(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def entries(self) -> List[LedgerEntry]:
        return list(self._entries)


class FileLedger:
    """Append-only JSONL ledger backed by a local file."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, entry: LedgerEntry) -> None:
        with open(self._path, "a") as f:
            f.write(entry.to_json() + "\n")

    def entries(self) -> List[LedgerEntry]:
        if not self._path.exists():
            return []
        out: List[LedgerEntry] = []
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if line:
                out.append(LedgerEntry.from_json(line))
        return out


class GitHubLedger:
    """Mirror ledger entries as comments on a GitHub tracking issue via `gh`.

    Reads are cached from the issue's comments; writes post a new comment.
    Any `gh`/network failure raises - a ledger that silently drops entries is
    worse than one that stops the run, because resumability depends on it.
    """

    _MARKER = "<!-- corticore-swarm-ledger -->"

    def __init__(self, repo: str, issue_number: int, runner=subprocess.run) -> None:
        self._repo = repo
        self._issue = issue_number
        self._runner = runner

    def record(self, entry: LedgerEntry) -> None:
        body = f"{self._MARKER}\n```json\n{entry.to_json()}\n```"
        self._runner(
            [
                "gh",
                "issue",
                "comment",
                str(self._issue),
                "--repo",
                self._repo,
                "--body",
                body,
            ],
            check=True,
        )

    def entries(self) -> List[LedgerEntry]:
        result = self._runner(
            [
                "gh",
                "issue",
                "view",
                str(self._issue),
                "--repo",
                self._repo,
                "--json",
                "comments",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout or "{}")
        out: List[LedgerEntry] = []
        for comment in payload.get("comments", []):
            body = comment.get("body", "")
            if self._MARKER not in body:
                continue
            fence = "```json"
            start = body.find(fence)
            if start == -1:
                continue
            start = body.find("\n", start) + 1
            end = body.find("```", start)
            if end == -1:
                continue
            out.append(LedgerEntry.from_json(body[start:end].strip()))
        return out
