"""Execution-backed deterministic scoring built on top of review localization."""

from __future__ import annotations

from arena.core.models import (
    BenchmarkCase,
    CaseResult,
    DeterministicCaseScore,
    DeterministicMetrics,
)
from arena.execution.test_executor import TestExecutionResult
from arena.patching.patch_models import PatchApplyResult
from arena.scoring.metrics import f_beta_score, precision, rate, recall
from arena.validators.base import ValidatorResult


def score_deterministic_case(
    case: BenchmarkCase,
    review: CaseResult,
    patch: PatchApplyResult,
    tests: TestExecutionResult | None,
    validators: list[ValidatorResult],
    beta: float,
) -> DeterministicCaseScore:
    # Detection is judged at file granularity (concept + file); line-level
    # localization is a separate, finer signal and never collapses a detected
    # bug into a miss.
    true_positives = review.bugs_matched
    false_negatives = max(review.bugs_total - review.bugs_matched, 0)
    false_positives = review.false_positive_count
    value_precision = precision(true_positives, false_positives)
    value_recall = recall(true_positives, false_negatives)
    structural_ran = bool(validators)
    structural_passed = all(item.passed for item in validators) if validators else None
    tests_ran = bool(tests and tests.ran)
    tests_passed = tests.passed if tests_ran and tests is not None else None
    patch_provided = bool(patch.patch_text.strip())
    reasons: list[str] = []

    if not review.bug_found:
        reasons.append("detection_failed")
    if patch.unsafe_paths:
        reasons.append("patch_unsafe_paths")
    if patch.touched_protected:
        reasons.append("patch_touched_protected_files")
    if case.validation.patch_required and not patch_provided:
        reasons.append("patch_required_but_missing")
    if case.validation.patch_required and not patch.applied:
        reasons.append("patch_apply_failed")
    tests_required = case.execution.run_tests or case.validation.tests_required
    if tests_required and tests_passed is not True:
        reasons.append("tests_failed")
    if case.validation.structural_validators and structural_passed is not True:
        reasons.append("structural_validation_failed")
    if false_positives > case.validation.max_false_positives:
        reasons.append("false_positive")

    return DeterministicCaseScore(
        case_id=case.id,
        detected_bug=review.bug_found,
        localized_correctly=review.correct_line,
        patch_provided=patch_provided,
        patch_applied=patch.applied,
        tests_ran=tests_ran,
        tests_passed=tests_passed,
        structural_validation_ran=structural_ran,
        structural_validation_passed=structural_passed,
        true_positive_count=true_positives,
        false_positive_count=false_positives,
        false_negative_count=false_negatives,
        precision=round(value_precision, 6),
        recall=round(value_recall, 6),
        f1=round(f_beta_score(value_precision, value_recall), 6),
        f_beta=round(f_beta_score(value_precision, value_recall, beta), 6),
        patch_apply_score=1.0 if patch.applied else 0.0,
        execution_score=1.0 if not tests_required or tests_passed else 0.0,
        structural_score=1.0 if not validators or structural_passed else 0.0,
        deterministic_pass=not reasons,
        failure_reasons=reasons,
    )


def aggregate_deterministic_metrics(
    cases: list[CaseResult],
    beta: float,
    total_cost: float,
    total_latency_ms: int,
) -> DeterministicMetrics:
    scores = [case.deterministic_case_score for case in cases if case.deterministic_case_score]
    detection_tp = sum(score.true_positive_count for score in scores)
    detection_fn = sum(score.false_negative_count for score in scores)
    fp = sum(score.false_positive_count for score in scores)
    case_count = len(scores)
    detection_precision = precision(detection_tp, fp)
    detection_recall = recall(detection_tp, detection_fn)
    detected_cases = sum(score.detected_bug for score in scores)
    localized_cases = sum(score.detected_bug and score.localized_correctly for score in scores)
    validated_tp = sum(score.deterministic_pass for score in scores)
    validated_fn = case_count - validated_tp
    validated_precision = precision(validated_tp, fp)
    validated_recall = recall(validated_tp, validated_fn)
    patch_provided = sum(score.patch_provided for score in scores)
    patch_applied = sum(score.patch_applied for score in scores)
    tests_ran = sum(score.tests_ran for score in scores)
    tests_passed = sum(score.tests_passed is True for score in scores)
    validation_ran = sum(score.structural_validation_ran for score in scores)
    validation_passed = sum(score.structural_validation_passed is True for score in scores)
    return DeterministicMetrics(
        detection_precision=round(detection_precision, 6),
        detection_recall=round(detection_recall, 6),
        detection_f1=round(f_beta_score(detection_precision, detection_recall), 6),
        detection_f_beta=round(f_beta_score(detection_precision, detection_recall, beta), 6),
        validated_precision=round(validated_precision, 6),
        validated_recall=round(validated_recall, 6),
        validated_f1=round(f_beta_score(validated_precision, validated_recall), 6),
        validated_f_beta=round(f_beta_score(validated_precision, validated_recall, beta), 6),
        beta=beta,
        deterministic_pass_rate=round(validated_tp / case_count, 6) if case_count else 0.0,
        # Unit-coherent case-level repair rate (see DeterministicMetrics). Equal
        # to deterministic_pass_rate; named for the leaderboard/product surface.
        validated_case_rate=round(validated_tp / case_count, 6) if case_count else 0.0,
        localization_rate=rate(localized_cases, detected_cases),
        patch_apply_rate=rate(patch_applied, patch_provided),
        test_pass_rate=rate(tests_passed, tests_ran),
        structural_pass_rate=rate(validation_passed, validation_ran),
        false_positives_per_case=round(fp / len(scores), 6) if scores else 0.0,
        cost_per_validated_fix=round(total_cost / validated_tp, 6) if validated_tp else None,
        latency_per_case_ms=round(total_latency_ms / len(scores), 2) if scores else 0.0,
    )
