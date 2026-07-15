"""Tests for operating-window math (pure, explicit `now`)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestrate"))

from swarm.window import OperatingWindow  # noqa: E402


def _window():
    return OperatingWindow(timezone="Asia/Kolkata", start="04:00", end="09:00", grace_minutes=15)


def test_is_open_inside_window():
    w = _window()
    now = datetime(2026, 7, 15, 5, 0, tzinfo=timezone.utc)  # tz-agnostic hour check
    local = now.replace(hour=5)
    assert w.is_open(local) is True


def test_is_closed_before_and_after():
    w = _window()
    before = datetime(2026, 7, 15, 3, 30)
    after = datetime(2026, 7, 15, 9, 30)
    assert w.is_open(before) is False
    assert w.is_open(after) is False


def test_seconds_until_close():
    w = _window()
    local = datetime(2026, 7, 15, 8, 30)
    assert w.seconds_until_close(local) == pytest.approx(30 * 60)


def test_seconds_until_close_zero_when_closed():
    w = _window()
    local = datetime(2026, 7, 15, 10, 0)
    assert w.seconds_until_close(local) == 0.0


def test_hard_deadline_adds_grace():
    w = _window()
    local = datetime(2026, 7, 15, 8, 0)
    deadline = w.hard_deadline_local(local)
    assert deadline.hour == 9 and deadline.minute == 15


def test_now_local_converts_timezone():
    w = _window()
    now_utc = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)
    local = w.now_local(now_utc)
    # Asia/Kolkata is UTC+5:30 -> 05:30 local.
    assert (local.hour, local.minute) == (5, 30)
