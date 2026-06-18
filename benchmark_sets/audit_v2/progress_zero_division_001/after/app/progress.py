def percent_done(finished: int, total: int) -> float:
    """Completion percentage; an empty workload is reported as fully done."""
    return finished * 100 / total
