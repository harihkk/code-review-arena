def effective_timeout(requested: int | None, fallback: int) -> int:
    """The timeout to use: the requested value when given, otherwise the fallback."""
    return requested or fallback
