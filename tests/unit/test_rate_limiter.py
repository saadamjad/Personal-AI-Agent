from app.services.rate_limiter import SlidingWindowRateLimiter


def test_sliding_window_allows_up_to_max() -> None:
    limiter = SlidingWindowRateLimiter(max_events=3, window_seconds=60)
    assert limiter.check("session-1")
    assert limiter.check("session-1")
    assert limiter.check("session-1")
    assert not limiter.check("session-1")


def test_sliding_window_is_per_key() -> None:
    limiter = SlidingWindowRateLimiter(max_events=1, window_seconds=60)
    assert limiter.check("a")
    assert limiter.check("b")
    assert not limiter.check("a")
