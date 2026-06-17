"""The single case-level repair is chosen unambiguously, never concatenated."""

from arena.benchmark.benchmark_runner import _select_case_patch
from arena.core.models import Finding, ReviewResult

PATCH_A = "--- a/app/a.py\n+++ b/app/a.py\n@@ -1 +1 @@\n-x\n+y\n"
PATCH_B = "--- a/app/b.py\n+++ b/app/b.py\n@@ -1 +1 @@\n-p\n+q\n"


def _finding(file: str, patch: str | None) -> Finding:
    return Finding(
        title="f",
        summary="f",
        category="correctness",
        severity="high",
        file=file,
        line_start=1,
        line_end=1,
        evidence="e",
        suggested_patch=patch,
        confidence=0.9,
    )


def _result(findings: list[Finding], proposed_patch: str | None = None) -> ReviewResult:
    return ReviewResult(
        findings=findings,
        proposed_patch=proposed_patch,
        overall_risk="high",
        review_summary="s",
    )


def test_case_level_patch_is_authoritative():
    # Even when findings carry their own patches, the case-level repair wins.
    result = _result([_finding("app/a.py", PATCH_A)], proposed_patch=PATCH_B)
    assert _select_case_patch(result) == (PATCH_B, "proposed_patch")


def test_single_finding_patch_is_adopted_for_legacy_reviewers():
    result = _result([_finding("app/a.py", PATCH_A), _finding("app/b.py", None)])
    assert _select_case_patch(result) == (PATCH_A, "single_finding")


def test_multiple_finding_patches_are_ambiguous_not_concatenated():
    result = _result([_finding("app/a.py", PATCH_A), _finding("app/b.py", PATCH_B)])
    assert _select_case_patch(result) == (None, "ambiguous")


def test_no_patch_anywhere():
    assert _select_case_patch(_result([_finding("app/a.py", None)])) == (None, "none")
    assert _select_case_patch(None) == (None, "none")


def test_blank_proposed_patch_falls_back_to_single_finding():
    result = _result([_finding("app/a.py", PATCH_A)], proposed_patch="   ")
    assert _select_case_patch(result) == (PATCH_A, "single_finding")
