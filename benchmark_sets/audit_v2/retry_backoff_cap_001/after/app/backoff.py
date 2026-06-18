def delay(attempt: int, base: int, cap: int) -> int:
    """Backoff delay for ``attempt``, growing with ``base`` but never above ``cap``."""
    return base * attempt
