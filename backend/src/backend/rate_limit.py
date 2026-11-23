from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from backend.auth import Clock, wall_clock


class _SlidingWindowCounter:

    def __init__(self, window_seconds: int, max_count: int) -> None:
        self._window = window_seconds
        self._max = max_count
        self._events: dict[str, list[datetime]] = defaultdict(list)

    def _prune(self, key: str, now: datetime) -> None:
        cutoff = now.timestamp() - self._window
        recent = [t for t in self._events.get(key, []) if t.timestamp() > cutoff]
        if recent:
            self._events[key] = recent
        else:
            self._events.pop(key, None)

    def check(self, key: str, clock: Clock | None = None) -> int | None:
        clk = clock or wall_clock
        now = clk.now()
        self._prune(key, now)
        if len(self._events.get(key, [])) >= self._max:
            oldest = self._events[key][0]
            retry_after = int(self._window - (now.timestamp() - oldest.timestamp())) + 1
            return max(retry_after, 1)
        return None

    def record(self, key: str, clock: Clock | None = None) -> None:
        clk = clock or wall_clock
        self._events[key].append(clk.now())


signup_limiter = _SlidingWindowCounter(window_seconds=3600, max_count=5)
login_fail_limiter = _SlidingWindowCounter(window_seconds=900, max_count=10)
chat_minute_limiter = _SlidingWindowCounter(window_seconds=60, max_count=6)


class _DailyCounter:

    def __init__(self, max_count: int) -> None:
        self._max = max_count
        self._counts: dict[str, int] = defaultdict(int)

    def check(self, key: str, clock: Clock | None = None) -> bool:
        clk = clock or wall_clock
        date_key = f"{key}:{clk.now().strftime('%Y-%m-%d')}"
        return self._counts[date_key] >= self._max

    def record(self, key: str, clock: Clock | None = None) -> None:
        clk = clock or wall_clock
        today = clk.now().strftime('%Y-%m-%d')
        # keys end with the UTC day; earlier days can never count again
        for stale in [k for k in self._counts if not k.endswith(f":{today}")]:
            del self._counts[stale]
        self._counts[f"{key}:{today}"] += 1


chat_daily_limiter = _DailyCounter(max_count=100)


def reset_all() -> None:
    signup_limiter._events.clear()
    login_fail_limiter._events.clear()
    chat_minute_limiter._events.clear()
    chat_daily_limiter._counts.clear()
