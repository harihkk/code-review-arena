"""Severity calibration scoring."""

from arena.core.models import Severity

ORDER: list[Severity] = ["low", "medium", "high", "critical"]


def severity_score(actual: Severity, expected: Severity) -> float:
    distance = abs(ORDER.index(actual) - ORDER.index(expected))
    if distance == 0:
        return 10
    if distance == 1:
        return 5
    return 0
