"""Severity calibration scoring."""

from arena.core.models import Severity

ORDER: list[Severity] = ["low", "medium", "high", "critical"]


def severity_ratio(actual: Severity, expected: Severity) -> float:
    """Return the 0..1 fraction of the severity weight earned."""
    distance = abs(ORDER.index(actual) - ORDER.index(expected))
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.5
    return 0.0
