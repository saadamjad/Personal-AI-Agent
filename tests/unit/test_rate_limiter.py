from app.services.rate_limiter import DailyCallBudget, SlidingWindowRateLimiter


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


def test_daily_budget_blocks_after_max() -> None:
    budget = DailyCallBudget(max_calls_per_day=2)
    assert budget.check_and_record()
    assert budget.check_and_record()
    assert not budget.check_and_record()
    status = budget.status()
    assert status["calls_in_window"] == 2
    assert status["max_calls"] == 2
