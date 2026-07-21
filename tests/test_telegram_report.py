"""Tests for the Telegram daily digest (pure; no network)."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.ledger import LedgerEntry  # noqa: E402
from swarm.telegram_report import (  # noqa: E402
    TelegramError,
    chat_ids_from_updates,
    entries_for_local_day,
    format_daily_report,
    send_telegram_message,
)


def _entry(cycle, role, status, summary, ts_utc: str) -> LedgerEntry:
    return LedgerEntry(
        cycle_id=cycle,
        task="corticore-maintenance",
        role=role,
        status=status,
        summary=summary,
        timestamp=ts_utc,
    )


def test_entries_for_local_day_filters_ist_day():
    # 2026-07-21 22:30 UTC == 2026-07-22 04:00 IST
    e_prev = _entry(
        "c1",
        "judge",
        "completed",
        "old",
        "2026-07-21T18:00:00+00:00",  # 23:30 IST Jul 21
    )
    e_today = _entry(
        "c2",
        "judge",
        "completed",
        "new",
        "2026-07-21T22:30:00+00:00",  # 04:00 IST Jul 22
    )
    e_next = _entry(
        "c3",
        "judge",
        "completed",
        "later",
        "2026-07-22T20:00:00+00:00",  # 01:30 IST Jul 23
    )
    day = date(2026, 7, 22)
    got = entries_for_local_day([e_prev, e_today, e_next], day, tz_name="Asia/Kolkata")
    assert [e.cycle_id for e in got] == ["c2"]


def test_format_daily_report_groups_by_cycle():
    entries = [
        _entry("aaa", "maintenance_scout", "completed", "fix CI flake", "2026-07-22T00:00:00+00:00"),
        _entry("aaa", "judge", "completed", "execute: fix CI flake", "2026-07-22T00:01:00+00:00"),
        _entry("aaa", "executor", "completed", "landed 2 commits", "2026-07-22T00:02:00+00:00"),
        _entry("bbb", "research_scout", "completed", "competitor: mem0 idea", "2026-07-22T01:00:00+00:00"),
    ]
    text = format_daily_report(
        entries, day=date(2026, 7, 22), commits_today=5, tz_name="Asia/Kolkata"
    )
    assert "Cycles: 2 | Commits on main: 5" in text
    assert "cycle aaa" in text
    assert "maintenance_scout: completed — fix CI flake" in text
    assert "cycle bbb" in text
    assert "research_scout: completed — competitor: mem0 idea" in text


def test_format_daily_report_empty_day():
    text = format_daily_report([], day=date(2026, 7, 22), commits_today=0)
    assert "No swarm cycles today." in text
    assert "Cycles: 0" in text


def test_format_daily_report_truncates_long_message():
    long = "x" * 500
    entries = [
        _entry("c", f"role{i}", "completed", long, "2026-07-22T00:00:00+00:00")
        for i in range(40)
    ]
    text = format_daily_report(
        entries, day=date(2026, 7, 22), commits_today=0, max_chars=800
    )
    assert len(text) <= 800
    assert "truncated" in text


def test_send_telegram_message_posts_expected_payload():
    calls = {}

    def fake_runner(url, payload):
        calls["url"] = url
        calls["payload"] = payload
        return json.dumps({"ok": True, "result": {"message_id": 1}}).encode()

    send_telegram_message("tok", "42", "hello", runner=fake_runner)
    assert calls["url"] == "https://api.telegram.org/bottok/sendMessage"
    body = calls["payload"].decode()
    assert "chat_id=42" in body
    assert "text=hello" in body
    assert "disable_web_page_preview=true" in body


def test_send_telegram_message_requires_creds():
    with pytest.raises(TelegramError, match="required"):
        send_telegram_message("", "1", "hi")


def test_send_telegram_message_raises_on_api_error():
    def fake_runner(url, payload):
        return json.dumps({"ok": False, "description": "bad"}).encode()

    with pytest.raises(TelegramError, match="API error"):
        send_telegram_message("tok", "1", "hi", runner=fake_runner)


def test_chat_ids_from_updates():
    updates = [
        {"message": {"chat": {"id": 111}}},
        {"message": {"chat": {"id": 111}}},
        {"channel_post": {"chat": {"id": -222}}},
    ]
    assert chat_ids_from_updates(updates) == ["111", "-222"]
