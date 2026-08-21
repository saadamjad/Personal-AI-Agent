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
