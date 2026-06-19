"""Multi-bug ground truth, applied weights, capped penalties, execution-backed fix quality."""

import random

import pydantic
import pytest

from arena.core.models import (
    MAX_BUGS_PER_CASE,
    MAX_FINDINGS_PER_RESPONSE,
    BenchmarkCase,
    Finding,
    GroundTruth,
    ReviewerResponse,
    ReviewResult,
)
from arena.patching.patch_models import PatchApplyResult
from arena.scoring.deterministic_scorer import score_deterministic_case
from arena.scoring.scorer import _max_weight_matching, apply_execution_fix_quality, score_case


def _matching_total(weights: dict, num_bugs: int) -> float:
    return sum(weights[(b, f)] for b, f in _max_weight_matching(weights, num_bugs).items())


def _brute_force_optimal_total(weights: dict, num_bugs: int) -> float:
    """Exhaustive maximum-weight matching, the slow reference oracle for tests."""
    findings = sorted({f for (_b, f) in weights})
    best = 0.0

    def rec(bug: int, used: frozenset, total: float) -> None:
        nonlocal best
        if bug == num_bugs:
            best = max(best, total)
            return
        rec(bug + 1, used, total)  # leave this bug unmatched
        for finding in findings:
            if finding not in used and (bug, finding) in weights:
                rec(bug + 1, used | {finding}, total + weights[(bug, finding)])

    rec(0, frozenset(), 0.0)
    return best


def test_max_weight_matching_beats_greedy_assignment():
    # finding 0 matches bug0 (10) and bug1 (9); finding 1 matches only bug0 (8).
    # Greedy takes the single best pair bug0<-finding0 (10) and leaves bug1
    # unmatched (total 10). The optimal assignment pairs bug1<-finding0 (9) and
    # bug0<-finding1 (8) for total 17, matching both bugs.
    weights = {(0, 0): 10.0, (1, 0): 9.0, (0, 1): 8.0}
    assert _max_weight_matching(weights, num_bugs=2) == {0: 1, 1: 0}


def test_max_weight_matching_single_bug_picks_highest_weight_finding():
    weights = {(0, 0): 3.0, (0, 1): 7.0, (0, 2): 5.0}
    assert _max_weight_matching(weights, num_bugs=1) == {0: 1}


def test_max_weight_matching_with_no_eligible_pairs_is_empty():
    assert _max_weight_matching({}, num_bugs=2) == {}


def test_max_weight_matching_leaves_extra_bugs_and_findings_unmatched():
    # Two bugs contend for one finding: the higher-weight bug wins, the other is
    # unmatched (the optimal total is 5, not 3).
    assert _max_weight_matching({(0, 0): 3.0, (1, 0): 5.0}, num_bugs=2) == {1: 0}
    # A bug with no eligible finding stays unmatched.
    assert _max_weight_matching({(0, 0): 4.0}, num_bugs=2) == {0: 0}


def test_max_weight_matching_is_deterministic_under_ties():
    # Two equally-good findings for one bug: the result is an optimum (weight 5)
    # and identical across calls, never dependent on iteration order.
    weights = {(0, 0): 5.0, (0, 1): 5.0}
    first = _max_weight_matching(weights, num_bugs=1)
    assert _matching_total(weights, num_bugs=1) == 5.0
    assert first == _max_weight_matching(weights, num_bugs=1)


def test_max_weight_matching_equals_brute_force_optimum_on_random_cases():
    # Property check: the Hungarian assignment achieves the exact optimum total
    # the exhaustive oracle finds, and always returns a valid injective matching.
    rng = random.Random(20260619)
    for _ in range(300):
        num_bugs = rng.randint(0, 4)
        num_findings = rng.randint(0, 5)
        weights = {
            (bug, finding): round(rng.uniform(0.1, 10.0), 3)
            for bug in range(num_bugs)
            for finding in range(num_findings)
            if rng.random() < 0.6
        }
        matching = _max_weight_matching(weights, num_bugs)
        assert len(set(matching.values())) == len(matching)  # injective
        assert all((bug, finding) in weights for bug, finding in matching.items())
        assert (
            abs(_matching_total(weights, num_bugs) - _brute_force_optimal_total(weights, num_bugs))
            < 1e-6
        )


def test_max_weight_matching_handles_large_allowed_input_fast():
    # At the schema caps the matrix is bounded, so the polynomial solver stays fast
    # and exact (no fallback). 40 bugs x 60 findings, all eligible.
    num_bugs, num_findings = 40, 60
    weights = {
        (bug, finding): float((bug * 7 + finding) % 13 + 1)
        for bug in range(num_bugs)
        for finding in range(num_findings)
    }
    matching = _max_weight_matching(weights, num_bugs=num_bugs)
    assert len(set(matching.values())) == len(matching)
    assert len(matching) == num_bugs  # findings >= bugs, so every bug matches


def test_review_result_rejects_too_many_findings():
    finding = Finding(
        title="t",
        summary="s",
        category="correctness",
        severity="low",
        file="a.py",
        line_start=1,
        line_end=1,
        evidence="e",
        confidence=0.5,
    )
    ReviewResult(findings=[finding], overall_risk="low", review_summary="ok")  # within cap
    with pytest.raises(pydantic.ValidationError):
        ReviewResult(
            findings=[finding] * (MAX_FINDINGS_PER_RESPONSE + 1),
            overall_risk="low",
            review_summary="too many",
        )


def test_ground_truth_rejects_too_many_bugs():
    bug = {
        "summary": "b",
        "files": [{"path": "a.py", "line_ranges": [{"start": 1, "end": 1}]}],
        "concepts": ["x"],
    }
    GroundTruth.model_validate({"bugs": [bug]})  # within cap
    with pytest.raises(pydantic.ValidationError):
        GroundTruth.model_validate({"bugs": [bug] * (MAX_BUGS_PER_CASE + 1)})


def _case(**overrides) -> BenchmarkCase:
    data = {
        "id": "synthetic_case",
        "title": "Synthetic case",
        "category": "correctness",
        "severity": "high",
        "stack": ["python"],
        "description": "Synthetic case for scorer tests.",
        "input": {},
        "ground_truth": {
            "bugs": [
                {
                    "summary": "Race condition on balance updates.",
                    "files": [{"path": "app/a.py", "line_ranges": [{"start": 5, "end": 10}]}],
                    "concepts": ["race condition"],
                    "must_mention": ["lock"],
                    "acceptable_fix_keywords": ["asyncio.lock", "lock"],
                },
                {
                    "summary": "SQL built by string concatenation.",
                    "files": [{"path": "app/b.py", "line_ranges": [{"start": 1, "end": 3}]}],
                    "concepts": ["sql injection"],
                    "must_mention": ["parameterize"],
                    "acceptable_fix_keywords": ["bind", "parameter"],
                },
            ],
        },
    }
    data.update(overrides)
    return BenchmarkCase.model_validate(data)


def _finding(file: str, start: int, end: int, text: str, fix: str) -> Finding:
    return Finding(
        title=text,
        summary=text,
        category="correctness",
        severity="high",
        file=file,
        line_start=start,
        line_end=end,
        evidence=text,
        suggested_fix=fix,
        confidence=0.9,
    )


def _response(findings: list[Finding]) -> ReviewerResponse:
    result = ReviewResult(findings=findings, overall_risk="high", review_summary="synthetic")
    return ReviewerResponse(raw_response=result.model_dump_json(), parsed_response=result)


BUG0_FINDING = _finding(
    "app/a.py", 5, 10, "Race condition: concurrent writes need a lock", "use asyncio.lock lock"
)
BUG1_FINDING = _finding(
    "app/b.py", 1, 3, "SQL injection: parameterize the query", "use bind parameter values"
)


def test_reporting_both_real_bugs_beats_reporting_one():
    case = _case()
    both = score_case(case, _response([BUG0_FINDING, BUG1_FINDING]))
    one = score_case(case, _response([BUG0_FINDING]))
    assert both.bugs_total == 2
    assert both.bugs_matched == 2
    assert both.false_positive_count == 0
    assert both.score == 100
    assert one.bugs_matched == 1
    # The second real finding is matched to the second bug, never penalized.
    assert both.score > one.score


def test_two_findings_cannot_both_claim_one_bug():
    case = _case()
    duplicate = _finding(
        "app/a.py", 5, 10, "Race condition needs a lock here too", "another lock fix"
    )
    result = score_case(case, _response([BUG0_FINDING, duplicate]))
    assert result.bugs_matched == 1
    matched = [item for item in result.scored_findings if item.is_true_positive]
    assert len(matched) == 1
    assert result.false_positive_count == 1


def test_acceptable_finding_is_neutral_not_false_positive():
    case = _case()
    case.ground_truth.acceptable_findings.extend(
        GroundTruth.model_validate(
            {
                "bugs": [case.ground_truth.bugs[0].model_dump()],
                "acceptable_findings": [{"path": "app/util.py", "concepts": ["logging"]}],
            }
        ).acceptable_findings
    )
    extra = _finding("app/util.py", 2, 2, "Missing logging around retries", "add logging")
    result = score_case(case, _response([BUG0_FINDING, BUG1_FINDING, extra]))
    assert result.false_positive_count == 0
    neutral = [item for item in result.scored_findings if item.is_neutral]
    assert len(neutral) == 1
    assert neutral[0].false_positive_reason == "acceptable_finding"
    # The no-false-positive bonus survives neutral findings.
    assert result.breakdown.no_false_positives == 5


def test_false_positive_penalty_is_capped():
    case = _case()
    junk = [
        _finding(f"junk/file{index}.py", 1, 1, f"Style nit {index}", "rename it")
        for index in range(6)
    ]
    result = score_case(case, _response([BUG0_FINDING, *junk]))
    assert result.false_positive_count == 6
    assert result.breakdown.false_positive_penalty == 15  # capped, not 30


def test_case_weights_are_actually_applied():
    case = _case()
    case.scoring.weights.concept_match = 70
    case.scoring.weights.file_match = 10
    case.scoring.weights.line_overlap = 5
    case.scoring.weights.severity_match = 5
    case.scoring.weights.fix_quality = 5
    case.scoring.weights.no_false_positives = 5
    result = score_case(case, _response([BUG0_FINDING, BUG1_FINDING]))
    assert result.breakdown.concept_match == 70
    assert result.breakdown.file_match == 10
    assert result.score == 100


def test_correct_line_derives_from_match_quality():
    case = _case()
    partial = _finding(
        "app/a.py", 8, 20, "Race condition: concurrent writes need a lock", "lock it"
    )
    same_file = _finding(
        "app/a.py", 1, 2, "Race condition: concurrent writes need a lock", "lock it"
    )
    partial_result = score_case(case, _response([partial]))
    same_file_result = score_case(case, _response([same_file]))
    assert partial_result.line_match == "partial"
    assert partial_result.correct_line is True
    assert same_file_result.line_match == "same_file"
    assert same_file_result.correct_line is False
    assert same_file_result.correct_file is True


def test_detection_no_longer_requires_line_precision():
    case = _case()
    same_file = _finding(
        "app/a.py", 1, 2, "Race condition: concurrent writes need a lock", "lock it"
    )
    review = score_case(case, _response([same_file, BUG1_FINDING]))
    patch = PatchApplyResult(
        case_id=case.id, applied=False, workspace_path="unused", patch_text="", duration_ms=1
    )
    deterministic = score_deterministic_case(case, review, patch, None, [], beta=1.0)
    assert deterministic.detected_bug is True
    assert deterministic.localized_correctly is False
    assert deterministic.true_positive_count == 2
    assert "localization_failed" not in deterministic.failure_reasons
    assert deterministic.deterministic_pass is True


def test_all_bugs_completeness_policy():
    case = _case()  # two seeded bugs; detection_requirement defaults to all_bugs
    patch = PatchApplyResult(
        case_id=case.id, applied=True, workspace_path="unused", patch_text="x", duration_ms=1
    )

    partial = score_case(case, _response([BUG0_FINDING]))
    det_partial = score_deterministic_case(case, partial, patch, None, [], beta=1.0)
    assert "incomplete_bug_detection" in det_partial.failure_reasons
    assert det_partial.deterministic_pass is False

    both = score_case(case, _response([BUG0_FINDING, BUG1_FINDING]))
    det_both = score_deterministic_case(case, both, patch, None, [], beta=1.0)
    assert "incomplete_bug_detection" not in det_both.failure_reasons
    assert det_both.deterministic_pass is True

    # at_least_one tolerates a partial review.
    case.validation.detection_requirement = "at_least_one"
    det_lenient = score_deterministic_case(case, partial, patch, None, [], beta=1.0)
    assert "incomplete_bug_detection" not in det_lenient.failure_reasons
    assert det_lenient.deterministic_pass is True

    # Finding nothing is a detection failure, not an incomplete detection.
    none_found = score_case(case, _response([]))
    det_none = score_deterministic_case(case, none_found, patch, None, [], beta=1.0)
    assert "detection_failed" in det_none.failure_reasons
    assert "incomplete_bug_detection" not in det_none.failure_reasons


def test_execution_overrides_keyword_fix_quality():
    single = _case()
    single.ground_truth.bugs = single.ground_truth.bugs[:1]
    stuffed = _finding(
        "app/a.py",
        5,
        10,
        "Race condition: concurrent writes need a lock",
        "asyncio.lock lock lock asyncio.lock",  # keyword stuffing: 2+ matches
    )
    weak = _finding(
        "app/a.py",
        5,
        10,
        "Race condition: concurrent writes need a lock",
        "serialize the read-modify-write so updates cannot interleave",  # correct, no keywords
    )
    stuffed_result = score_case(single, _response([stuffed]))
    weak_result = score_case(single, _response([weak]))
    assert stuffed_result.breakdown.fix_quality == 15
    assert weak_result.breakdown.fix_quality == 3

    failed = apply_execution_fix_quality(single, stuffed_result, validated=False)
    validated = apply_execution_fix_quality(single, weak_result, validated=True)
    assert failed.breakdown.fix_quality == 8  # stuffing without a working patch is capped
    assert validated.breakdown.fix_quality == 15  # working patch earns full weight
    assert validated.score > weak_result.score


def test_legacy_primary_bug_shape_still_loads_and_serializes():
    legacy = GroundTruth.model_validate(
        {
            "primary_bug": {
                "summary": "Race condition.",
                "files": [{"path": "app/a.py", "line_ranges": [{"start": 5, "end": 10}]}],
                "concepts": ["race condition"],
                "must_mention": ["lock"],
                "acceptable_fix_keywords": ["lock"],
            }
        }
    )
    assert len(legacy.bugs) == 1
    assert legacy.primary_bug.summary == "Race condition."
    dumped = legacy.model_dump()
    assert dumped["primary_bug"]["summary"] == "Race condition."
    assert GroundTruth.model_validate(dumped).primary_bug.summary == "Race condition."
