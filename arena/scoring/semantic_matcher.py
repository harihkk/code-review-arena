"""Deprecated alias for :mod:`arena.scoring.concept_matcher`.

The matcher is lexical, not semantic; the module was renamed so the name stops
implying capability it does not have. This shim keeps old imports working for
one release.
"""

from __future__ import annotations

from arena.core.models import BenchmarkCase, Finding
from arena.scoring.concept_matcher import concept_ratio, mentions  # noqa: F401


def concept_score(finding: Finding, case: BenchmarkCase) -> float:
    """Legacy 0..35 concept score for the primary bug."""
    return round(concept_ratio(finding, case.ground_truth.primary_bug, case.category) * 35, 2)
