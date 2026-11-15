"""In-memory rate limiting (F15). All counters reset on restart."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from backend.auth import Clock, wall_clock


class _SlidingWindowCounter:
    """Counts events in a sliding window."""

    def __init__(self, window_seconds: int, max_count: int) -> None:
        self._window = window_seconds
        self._max = max_count
        self._events: dict[str, list[datetime]] = defaultdict(list)

    def _prune(self, key: str, now: datetime) -> None:
        cutoff = now.timestamp() - self._window
        self._events[key] = [
            t for t in self._events[key] if t.timestamp() > cutoff
        ]

    def check(self, key: str, clock: Clock | None = None) -> int | None:
        """Return seconds until retry if limited, else None."""
        clk = clock or wall_clock
        now = clk.now()
        self._prune(key, now)
        if len(self._events[key]) >= self._max:
            oldest = self._events[key][0]
            retry_after = int(self._window - (now.timestamp() - oldest.timestamp())) + 1
            return max(retry_after, 1)
        return None

    def record(self, key: str, clock: Clock | None = None) -> None:
        clk = clock or wall_clock
        self._events[key].append(clk.now())


signup_limiter = _SlidingWindowCounter(window_seconds=3600, max_count=5)
login_fail_limiter = _SlidingWindowCounter(window_seconds=900, max_count=10)


def reset_all() -> None:
    signup_limiter._events.clear()
    login_fail_limiter._events.clear()
