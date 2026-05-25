"""Suggested-fix quality approximation."""

from arena.core.models import BenchmarkCase, Finding


def fix_quality_score(finding: Finding, case: BenchmarkCase) -> float:
    fix = (finding.suggested_fix or "").casefold().strip()
    if not fix:
        return 0
    keywords = case.ground_truth.primary_bug.acceptable_fix_keywords
    matches = sum(keyword.casefold() in fix for keyword in keywords)
    if matches >= 2:
        return 15
    if matches == 1:
        return 8
    return 3
