"""Multi-bug ground truth, applied weights, capped penalties, execution-backed fix quality."""

from arena.core.models import (
    BenchmarkCase,
    Finding,
    GroundTruth,
    ReviewerResponse,
    ReviewResult,
)
from arena.patching.patch_models import PatchApplyResult
from arena.scoring.deterministic_scorer import score_deterministic_case
from arena.scoring.scorer import _max_weight_matching, apply_execution_fix_quality, score_case


def test_max_weight_matching_beats_greedy_assignment():
    # finding 0 matches bug0 (10) and bug1 (9); finding 1 matches only bug0 (8).
    # Greedy takes the single best pair bug0<-finding0 (10) and leaves bug1
    # unmatched (total 10). The optimal assignment pairs bug1<-finding0 (9) and
    # bug0<-finding1 (8) for total 17, matching both bugs.
    weights = {(0, 0): 10.0, (1, 0): 9.0, (0, 1): 8.0}
    assert _max_weight_matching(weights, num_bugs=2) == {0: 1, 1: 0}


def test_max_weight_matching_single_bug_picks_highest_weight_finding():
    # The single-bug case (every shipped case today): pick the best finding, so
    # the result is identical to the old greedy assignment.
    weights = {(0, 0): 3.0, (0, 1): 7.0, (0, 2): 5.0}
    assert _max_weight_matching(weights, num_bugs=1) == {0: 1}


def test_max_weight_matching_with_no_eligible_pairs_is_empty():
    assert _max_weight_matching({}, num_bugs=2) == {}


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
