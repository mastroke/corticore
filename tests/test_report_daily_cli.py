"""Tests for report_daily.py CLI wiring (dry-run; no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

import report_daily  # noqa: E402
from swarm.ledger import FileLedger, LedgerEntry  # noqa: E402


def test_dry_run_prints_empty_digest(tmp_path, capsys):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("")
    code = report_daily.main(
        ["--dry-run", "--ledger", str(ledger), "--checkout", str(tmp_path / "missing")],
        env={},
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "No swarm cycles today." in out
    assert "corticore swarm" in out


def test_dry_run_includes_ledger_entries(tmp_path, capsys):
    ledger_path = tmp_path / "ledger.jsonl"
    fl = FileLedger(ledger_path)
    # Timestamp "now" in UTC so it matches today's filter in most timezones;
    # build_report_text uses Asia/Kolkata — use an explicit recent ISO that
    # lands on "today" IST by writing via build_report_text's day override path.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    noon_ist = datetime(
        today.year, today.month, today.day, 5, 0, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    fl.record(
        LedgerEntry(
            cycle_id="abc123",
            task="corticore-maintenance",
            role="judge",
            status="completed",
            summary="execute: something useful",
            timestamp=noon_ist.astimezone().isoformat(),
        )
    )
    code = report_daily.main(
        ["--dry-run", "--ledger", str(ledger_path), "--checkout", str(tmp_path)],
        env={},
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "cycle abc123" in out
    assert "judge: completed" in out


def test_send_without_creds_fails(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("")
    code = report_daily.main(
        ["--ledger", str(ledger), "--checkout", str(tmp_path)],
        env={},
    )
    assert code == 1


def test_print_chat_id_without_token_fails():
    code = report_daily.main(["--print-chat-id"], env={})
    assert code == 1
