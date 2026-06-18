def percent_done(finished: int, total: int) -> float:
    """Completion percentage; an empty workload is reported as fully done."""
    if total == 0:
        return 100.0
    return finished * 100 / total
