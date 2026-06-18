from app.ledger import min_balance


def test_tracks_the_dip_below_start():
    # Balances visited: 70, 20, 40. The trough is 20.
    assert min_balance(100, [-30, -50, 20]) == 20


def test_start_is_the_floor_when_balance_only_grows():
    assert min_balance(10, [5, 5, 5]) == 10


def test_no_movement_returns_start():
    assert min_balance(42, []) == 42


def test_dip_can_go_negative():
    assert min_balance(0, [10, -25, 5]) == -15
