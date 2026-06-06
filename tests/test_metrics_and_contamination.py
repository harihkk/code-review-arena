"""Pin the six headline metrics (incl. beta weighting) and the contamination guard."""

from __future__ import annotations

from pathlib import Path

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.case_loader import load_cases
from arena.core.models import (
    CaseResult,
    DeterministicCaseScore,
    Finding,
    ReviewerResponse,
    ReviewResult,
    ScoreBreakdown,
)
from arena.reviewers.mock import MockReviewer
from arena.scoring.deterministic_scorer import aggregate_deterministic_metrics
from arena.scoring.metrics import f_beta_score, precision, recall
from arena.scoring.scorer import score_case

AUDIT = Path("benchmark_sets/audit_v1")


def _scored_case(
    index: int,
    *,
    detected: bool,
    deterministic_pass: bool,
    patch_applied: bool,
    tests_passed: bool,
    structural_passed: bool,
    false_positives: int,
) -> CaseResult:
    score = DeterministicCaseScore(
        case_id=f"case_{index}",
        detected_bug=detected,
        localized_correctly=detected,
        patch_provided=True,
        patch_applied=patch_applied,
        tests_ran=True,
        tests_passed=tests_passed,
        structural_validation_ran=True,
        structural_validation_passed=structural_passed,
        true_positive_count=1 if detected else 0,
        false_positive_count=false_positives,
        false_negative_count=0 if detected else 1,
        precision=0.0,
        recall=0.0,
        f1=0.0,
        f_beta=0.0,
        patch_apply_score=1.0 if patch_applied else 0.0,
        execution_score=1.0 if tests_passed else 0.0,
        structural_score=1.0 if structural_passed else 0.0,
        deterministic_pass=deterministic_pass,
        failure_reasons=[],
    )
    return CaseResult(
        case_id=f"case_{index}",
        title=f"case_{index}",
        category="security",
        severity="high",
        ground_truth_summary="seeded bug",
        response=ReviewerResponse(raw_response=""),
        scored_findings=[],
        breakdown=ScoreBreakdown(),
        score=0.0,
        bug_found=detected,
        correct_file=detected,
        correct_line=detected,
        line_match="exact" if detected else "wrong_file",
        false_positive_count=false_positives,
        deterministic_case_score=score,
        deterministic_pass=deterministic_pass,
    )


def _synthetic_run() -> list[CaseResult]:
    # 10 cases: 8 detected+localized, 5 validated, 9 patches applied, 7 tests pass,
    # 6 structural pass, 4 false positives total (all on one case).
    cases: list[CaseResult] = []
    for i in range(10):
        cases.append(
            _scored_case(
                i,
                detected=i < 8,
                deterministic_pass=i < 5,
                patch_applied=i < 9,
                tests_passed=i < 7,
                structural_passed=i < 6,
                false_positives=4 if i == 0 else 0,
            )
        )
    return cases


def test_six_headline_metrics_match_their_formulas():
    cases = _synthetic_run()
    metrics = aggregate_deterministic_metrics(cases, beta=1.0, total_cost=0.0, total_latency_ms=0)

    # Detection: tp=8, fp=4, fn=2.
    expected_detection = f_beta_score(precision(8, 4), recall(8, 2), 1.0)
    assert metrics.detection_f_beta == round(expected_detection, 6)
    # Validation: tp=5 (deterministic passes), fp=4, fn=5.
    expected_validated = f_beta_score(precision(5, 4), recall(5, 5), 1.0)
    assert metrics.validated_f_beta == round(expected_validated, 6)

    assert metrics.patch_apply_rate == 0.9  # 9/10 applied
    assert metrics.test_pass_rate == 0.7  # 7/10 passed
    assert metrics.structural_pass_rate == 0.6  # 6/10 passed
    assert metrics.false_positives_per_case == 0.4  # 4/10
    assert metrics.deterministic_pass_rate == 0.5  # 5/10


def test_beta_weighting_favours_recall_as_beta_grows():
    cases = _synthetic_run()
    # Detection recall (0.8) exceeds precision (0.667), so a recall-weighted beta
    # must score higher than a precision-weighted one.
    low = aggregate_deterministic_metrics(cases, 0.5, 0.0, 0).detection_f_beta
    mid = aggregate_deterministic_metrics(cases, 1.0, 0.0, 0).detection_f_beta
    high = aggregate_deterministic_metrics(cases, 2.0, 0.0, 0).detection_f_beta
    assert low < mid < high
    assert mid == round(f_beta_score(precision(8, 4), recall(8, 2), 1.0), 6)
    assert high == round(f_beta_score(precision(8, 4), recall(8, 2), 2.0), 6)


def test_reviewer_cannot_pass_on_metadata_alone():
    """A finding with the right category/severity but the wrong location is not a hit."""
    case = load_cases(AUDIT)[0]
    response = ReviewerResponse(
        raw_response="{}",
        parsed_response=ReviewResult(
            findings=[
                Finding(
                    title="Something is wrong",
                    summary="There may be an issue here.",
                    category=case.category,  # correct metadata...
                    severity=case.severity,  # ...correct metadata...
                    file="totally/unrelated/path.py",  # ...but wrong location.
                    line_start=1,
                    line_end=1,
                    evidence="none",
                    confidence=0.9,
                )
            ],
            overall_risk=case.severity,
            review_summary="guess",
        ),
    )
    result = score_case(case, response)
    assert result.bug_found is False
    assert result.correct_file is False
    assert result.false_positive_count == 1


def test_empty_review_detects_nothing():
    case = load_cases(AUDIT)[0]
    response = ReviewerResponse(
        raw_response="{}",
        parsed_response=ReviewResult(findings=[], overall_risk="none", review_summary="nothing"),
    )
    result = score_case(case, response)
    assert result.bug_found is False
    assert result.false_positive_count == 0


def test_false_positive_patch_control_detects_but_does_not_validate(tmp_path):
    run = run_benchmark(
        AUDIT,
        MockReviewer("false_positive_patch"),
        output_dir=tmp_path / "runs",
        db_path=tmp_path / "arena.db",
        mode="full",
        allow_local_execution=True,
    )
    metrics = run.deterministic_metrics
    assert metrics is not None
    # Unsupported extra findings drag detection precision below 1 and block validation.
    assert run.false_positives > 0
    assert metrics.detection_f_beta < 1
    assert metrics.validated_f_beta == 0
    assert all(not result.deterministic_pass for result in run.case_results)
