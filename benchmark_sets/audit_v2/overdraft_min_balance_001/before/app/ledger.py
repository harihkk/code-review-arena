def min_balance(start: int, deltas: list[int]) -> int:
    """The smallest balance reached while applying ``deltas`` to ``start`` in order."""
    balance = start
    seen = start
    for delta in deltas:
        balance = balance + delta
        if balance < seen:
            seen = balance
    return seen
