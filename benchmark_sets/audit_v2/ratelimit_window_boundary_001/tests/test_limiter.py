from app.limiter import allow


def test_allows_when_below_the_cap():
    assert allow([1, 2], now=5, limit=3, window=10) is True


def test_refuses_once_the_cap_is_reached():
    # Two requests already inside the window with a cap of two: the next is refused.
    assert allow([1, 2], now=5, limit=2, window=10) is False


def test_requests_outside_the_window_are_ignored():
    # At now=5 with a window of 3, anything at or before t=2 has aged out.
    assert allow([1, 4], now=5, limit=1, window=3) is False
    assert allow([1], now=5, limit=1, window=3) is True
