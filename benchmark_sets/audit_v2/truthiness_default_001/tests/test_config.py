from app.config import effective_timeout


def test_uses_requested_value():
    assert effective_timeout(5, 30) == 5


def test_explicit_zero_is_respected():
    assert effective_timeout(0, 30) == 0


def test_missing_falls_back():
    assert effective_timeout(None, 30) == 30
