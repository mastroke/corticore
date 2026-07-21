#!/usr/bin/env python3
"""Send (or print) today's corticore swarm digest via Telegram.

Scheduled by ``deploy/systemd/corticore-swarm-report.timer`` at 09:30
Asia/Kolkata. Reads the local FileLedger and optional dedicated checkout
commit count, then posts one plain-text message.

Usage:
    python orchestrate/report_daily.py
    python orchestrate/report_daily.py --dry-run
    python orchestrate/report_daily.py --print-chat-id

Env:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (required to send)
    SWARM_LEDGER_PATH (optional; default orchestrate/.swarm_ledger.jsonl)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ORCHESTRATE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ORCHESTRATE_DIR))

from swarm.gitops import DEFAULT_CHECKOUT, count_commits_today  # noqa: E402
from swarm.ledger import FileLedger  # noqa: E402
from swarm.telegram_report import (  # noqa: E402
    DEFAULT_TIMEZONE,
    TelegramError,
    chat_ids_from_updates,
    entries_for_local_day,
    fetch_telegram_updates,
    format_daily_report,
    send_telegram_message,
)

DEFAULT_LEDGER = ORCHESTRATE_DIR / ".swarm_ledger.jsonl"


def _today_local(tz_name: str = DEFAULT_TIMEZONE):
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:  # noqa: BLE001
        return datetime.now().astimezone().date()


def _commits_today(checkout: Path) -> int:
    if not checkout.exists() or not (checkout / ".git").exists():
        return 0
    try:
        return count_commits_today(checkout)
    except Exception:  # noqa: BLE001 - report still useful without commit count
        return 0


def build_report_text(
    *,
    ledger_path: Path,
    checkout: Path,
    day=None,
    tz_name: str = DEFAULT_TIMEZONE,
) -> str:
    day = day or _today_local(tz_name)
    ledger = FileLedger(ledger_path)
    todays = entries_for_local_day(ledger.entries(), day, tz_name=tz_name)
    commits = _commits_today(checkout)
    return format_daily_report(
        todays, day=day, commits_today=commits, tz_name=tz_name
    )


def main(argv: Optional[list] = None, env: Optional[dict] = None) -> int:
    env = env if env is not None else os.environ
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the digest and do not call Telegram.",
    )
    parser.add_argument(
        "--print-chat-id",
        action="store_true",
        help="Call getUpdates and print chat ids (message the bot first).",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Path to the swarm JSONL ledger.",
    )
    parser.add_argument(
        "--checkout",
        type=Path,
        default=DEFAULT_CHECKOUT,
        help="Dedicated swarm checkout (for commits-today count).",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help="Timezone for the 'today' filter (default Asia/Kolkata).",
    )
    args = parser.parse_args(argv)

    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (env.get("TELEGRAM_CHAT_ID") or "").strip()

    if args.print_chat_id:
        if not token:
            print("TELEGRAM_BOT_TOKEN is not set.", file=sys.stderr)
            return 1
        try:
            updates = fetch_telegram_updates(token)
        except TelegramError as exc:
            print(f"failed to fetch updates: {exc}", file=sys.stderr)
            return 1
        ids = chat_ids_from_updates(updates)
        if not ids:
            print(
                "No chats found. Open Telegram, message your bot once, then retry.",
                file=sys.stderr,
            )
            return 1
        print("Chat id(s) from recent updates:")
        for cid in ids:
            print(cid)
        return 0

    ledger_path = Path(
        args.ledger
        or env.get("SWARM_LEDGER_PATH")
        or DEFAULT_LEDGER
    ).expanduser()
    checkout = Path(args.checkout).expanduser()
    text = build_report_text(
        ledger_path=ledger_path, checkout=checkout, tz_name=args.timezone
    )

    if args.dry_run:
        print(text, end="" if text.endswith("\n") else "\n")
        return 0

    if not token or not chat_id:
        print(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set to send. "
            "Use --dry-run to preview, or --print-chat-id after messaging the bot.",
            file=sys.stderr,
        )
        return 1

    try:
        send_telegram_message(token, chat_id, text)
    except TelegramError as exc:
        print(f"failed to send Telegram report: {exc}", file=sys.stderr)
        return 1

    print("[report] sent daily swarm digest to Telegram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
