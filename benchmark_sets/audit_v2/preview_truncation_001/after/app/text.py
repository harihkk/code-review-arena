def preview(text: str, limit: int) -> str:
    """Shorten ``text`` to ``limit`` characters, marking it when it is longer."""
    if len(text) > limit:
        return text[:limit - 1] + "..."
    return text
