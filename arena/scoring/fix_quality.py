"""Suggested-fix quality heuristics.

Keyword counting is a weak textual signal and is treated as such: in full mode
the benchmark runner overrides it with execution evidence (did the patch apply
and pass the case's tests and validators) via
:func:`arena.scoring.scorer.apply_execution_fix_quality`. Without execution
evidence the keyword score is capped at ``WEAK_FIX_CAP``.
"""

from arena.core.models import Finding, GroundTruthBug

# Highest fraction of the fix-quality weight a textual heuristic can earn
# when execution evidence is absent or negative.
WEAK_FIX_CAP = 8 / 15


def fix_quality_ratio(finding: Finding, bug: GroundTruthBug) -> float:
    """Return the 0..1 fraction of the fix-quality weight earned by keywords."""
    fix = (finding.suggested_fix or "").casefold().strip()
    if not fix:
        return 0.0
    matches = sum(keyword.casefold() in fix for keyword in bug.acceptable_fix_keywords)
    if matches >= 2:
        return 1.0
    if matches == 1:
        return 8 / 15
    return 3 / 15
