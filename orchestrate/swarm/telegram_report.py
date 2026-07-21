"""Deterministic daily digest of swarm ledger activity for Telegram.

No LLM in the loop: filter today's ledger entries (Asia/Kolkata by default),
format a short plain-text report, and POST it to the Telegram Bot API.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import date, datetime, timezone
from typing import Callable, Iterable, List, Optional, Sequence

from .ledger import LedgerEntry

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

DEFAULT_TIMEZONE = "Asia/Kolkata"
# Telegram hard limit is 4096; stay under with headroom for truncation notice.
MAX_MESSAGE_CHARS = 3500
MAX_SUMMARY_CHARS = 120


class TelegramError(RuntimeError):
    """Raised when the Telegram Bot API rejects a call."""


def _parse_entry_ts(entry: LedgerEntry) -> Optional[datetime]:
    raw = (entry.timestamp or "").strip()
    if not raw:
        return None
    try:
        # Support trailing Z.
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def entries_for_local_day(
    entries: Sequence[LedgerEntry],
    day: date,
    tz_name: str = DEFAULT_TIMEZONE,
) -> List[LedgerEntry]:
    """Return ledger entries whose timestamp falls on `day` in `tz_name`."""
    if ZoneInfo is None:  # pragma: no cover
        tz = timezone.utc
    else:
        tz = ZoneInfo(tz_name)
    out: List[LedgerEntry] = []
    for entry in entries:
        dt = _parse_entry_ts(entry)
        if dt is None:
            continue
        if dt.astimezone(tz).date() == day:
            out.append(entry)
    return out


def _truncate(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def format_daily_report(
    entries: Sequence[LedgerEntry],
    *,
    day: date,
    commits_today: int = 0,
    tz_name: str = DEFAULT_TIMEZONE,
    max_chars: int = MAX_MESSAGE_CHARS,
) -> str:
    """Build a plain-text digest grouped by cycle_id."""
    cycles: "OrderedDict[str, List[LedgerEntry]]" = OrderedDict()
    for entry in entries:
        cycles.setdefault(entry.cycle_id, []).append(entry)

    lines: List[str] = [
        f"corticore swarm — {day.isoformat()} ({tz_name})",
        "",
        f"Cycles: {len(cycles)} | Commits on main: {commits_today}",
        "",
    ]

    if not cycles:
        lines.append("No swarm cycles today.")
        return "\n".join(lines)

    for cycle_id, cycle_entries in cycles.items():
        lines.append(f"cycle {cycle_id}")
        # Keep last status per role (ledger is append-only).
        by_role: "OrderedDict[str, LedgerEntry]" = OrderedDict()
        for entry in cycle_entries:
            by_role[entry.role] = entry
        for role, entry in by_role.items():
            summary = _truncate(entry.summary)
            if summary:
                lines.append(f"  {role}: {entry.status} — {summary}")
            else:
                lines.append(f"  {role}: {entry.status}")
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    if len(text) <= max_chars:
        return text
    notice = "\n…(truncated for Telegram)\n"
    return text[: max_chars - len(notice)] + notice


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    *,
    runner: Optional[Callable[..., object]] = None,
) -> dict:
    """POST text to Telegram Bot API sendMessage. Returns parsed JSON body."""
    if not token or not chat_id:
        raise TelegramError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    if runner is None:
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"Telegram network error: {exc.reason}") from exc
    else:
        body_obj = runner(url, payload)
        if isinstance(body_obj, bytes):
            body = body_obj.decode("utf-8")
        elif isinstance(body_obj, str):
            body = body_obj
        else:
            body = json.dumps(body_obj)

    data = json.loads(body)
    if not data.get("ok"):
        raise TelegramError(f"Telegram API error: {data}")
    return data


def fetch_telegram_updates(
    token: str,
    *,
    runner: Optional[Callable[..., object]] = None,
) -> List[dict]:
    """Return recent getUpdates results (for discovering chat ids)."""
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is required")
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    if runner is None:
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"Telegram network error: {exc.reason}") from exc
    else:
        body_obj = runner(url, None)
        body = body_obj.decode("utf-8") if isinstance(body_obj, bytes) else str(body_obj)

    data = json.loads(body)
    if not data.get("ok"):
        raise TelegramError(f"Telegram API error: {data}")
    return list(data.get("result") or [])


def chat_ids_from_updates(updates: Iterable[dict]) -> List[str]:
    """Extract distinct chat ids from getUpdates payloads."""
    seen = []
    for upd in updates:
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        if cid is None:
            continue
        s = str(cid)
        if s not in seen:
            seen.append(s)
    return seen
