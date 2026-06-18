def allow(history: list[int], *, now: int, limit: int, window: int) -> bool:
    """Whether a request at ``now`` fits within ``limit`` requests per ``window`` seconds."""
    recent = [stamp for stamp in history if stamp > now - window]
    return len(recent) <= limit
