from app.backoff import delay


def test_grows_with_attempt():
    assert delay(2, 10, 100) == 20


def test_never_exceeds_the_ceiling():
    assert delay(20, 10, 100) == 100


def test_at_the_ceiling_returns_the_ceiling():
    assert delay(10, 10, 100) == 100
