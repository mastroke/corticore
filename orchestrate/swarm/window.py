"""Operating-window math: when the swarm may work and when it must stop.

The swarm runs inside a daily window (default 04:00-09:00 Asia/Kolkata). New
work is only started while the window is open, and any run still going after
a grace period past the window end is cancelled. All logic here is pure
(takes an explicit `now`) so schedule behaviour is fully testable without
waiting for a wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

try:  # Python 3.9+ standard library
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - only on very old runtimes
    ZoneInfo = None  # type: ignore[assignment]


def _parse_hhmm(value: str) -> tuple:
    hh, mm = value.split(":")
    return int(hh), int(mm)


@dataclass(frozen=True)
class OperatingWindow:
    timezone: str
    start: str  # "HH:MM"
    end: str  # "HH:MM"
    grace_minutes: int = 15

    def _tz(self):
        if ZoneInfo is None:  # pragma: no cover
            return None
        return ZoneInfo(self.timezone)

    def now_local(self, now_utc: Optional[datetime] = None) -> datetime:
        from datetime import timezone as _tz

        now_utc = now_utc or datetime.now(_tz.utc)
        tz = self._tz()
        return now_utc.astimezone(tz) if tz else now_utc

    def is_open(self, now_local: datetime) -> bool:
        start_h, start_m = _parse_hhmm(self.start)
        end_h, end_m = _parse_hhmm(self.end)
        start = now_local.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        end = now_local.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        return start <= now_local < end

    def seconds_until_close(self, now_local: datetime) -> float:
        """Seconds from `now_local` to the window end (0 if already closed)."""
        end_h, end_m = _parse_hhmm(self.end)
        end = now_local.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        delta = (end - now_local).total_seconds()
        return max(0.0, delta)

    def hard_deadline_local(self, now_local: datetime) -> datetime:
        """Window end plus the grace period - the point after which running
        agents are cancelled."""
        end_h, end_m = _parse_hhmm(self.end)
        end = now_local.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        return end + timedelta(minutes=self.grace_minutes)
