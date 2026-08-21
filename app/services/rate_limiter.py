import threading
import time
from collections import defaultdict, deque

_WINDOW_SECONDS = 600  # 10 minutes


class SlidingWindowRateLimiter:
    """In-memory sliding-window limiter. Adequate at single-instance scale;
    would need a shared backend (e.g. Redis) if the service ever runs
    multiple instances behind a load balancer."""

    def __init__(self, max_events: int, window_seconds: int = _WINDOW_SECONDS) -> None:
        self._max_events = max_events
        self._window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Returns True if the event is allowed, False if the key is rate-limited."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self._max_events:
                return False
            events.append(now)
            return True


class DailyCallBudget:
    """In-memory sliding 24h ceiling on real LLM calls — a backstop, not a
    replacement for provider-side spend caps."""

    def __init__(self, max_calls_per_day: int) -> None:
        self._max_calls = max_calls_per_day
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def check_and_record(self) -> bool:
        now = time.monotonic()
        cutoff = now - 86_400
        with self._lock:
            while self._calls and self._calls[0] < cutoff:
                self._calls.popleft()
            if len(self._calls) >= self._max_calls:
                return False
            self._calls.append(now)
            return True

    def status(self) -> dict[str, int]:
        with self._lock:
            return {"calls_in_window": len(self._calls), "max_calls": self._max_calls}
