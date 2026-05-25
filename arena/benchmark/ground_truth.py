"""Helpers for isolating scoring metadata from reviewer input."""

from arena.core.models import BenchmarkCase


def reviewer_safe_metadata(case: BenchmarkCase) -> dict[str, object]:
    """Return descriptive metadata while deliberately excluding ground truth."""
    return {
        "id": case.id,
        "title": case.title,
        "category": case.category,
        "stack": case.stack,
        "description": case.description,
    }
