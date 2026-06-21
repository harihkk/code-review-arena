"""Phase 1B commit 1: strict, bounded external/reviewer/API schema contract."""

import pytest
from pydantic import ValidationError

from arena.core import limits
from arena.core.models import (
    AcceptableFinding,
    CaseInput,
    ExecutionConfig,
    Finding,
    GroundTruthBug,
    GroundTruthFile,
    LineRange,
    MetricsConfig,
    ReviewResult,
    ScoreWeights,
    ScoringConfig,
    ValidationConfig,
)
from arena.server.schemas import CreateRunRequest


def _finding(**overrides):
    base = {
        "title": "t",
        "summary": "s",
        "category": "correctness",
        "severity": "high",
        "file": "app.py",
        "line_start": 1,
        "line_end": 2,
        "evidence": "e",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


# Valid minimal kwargs per external/reviewer/API model, for the unknown-field sweep.
VALID_KWARGS = {
    LineRange: {"start": 1, "end": 2},
    GroundTruthFile: {"path": "a.py", "line_ranges": [{"start": 1, "end": 1}]},
    GroundTruthBug: {
        "summary": "s",
        "files": [{"path": "a.py", "line_ranges": [{"start": 1, "end": 1}]}],
        "concepts": ["c"],
    },
    AcceptableFinding: {"concepts": ["c"]},
    CaseInput: {},
    ScoreWeights: {},
    ScoringConfig: {},
    ExecutionConfig: {},
    ValidationConfig: {},
    MetricsConfig: {},
    Finding: _finding(),
    ReviewResult: {"findings": [], "overall_risk": "none", "review_summary": "x"},
    CreateRunRequest: {},
}


@pytest.mark.parametrize("model", list(VALID_KWARGS), ids=lambda m: m.__name__)
def test_every_strict_model_rejects_unknown_fields(model):
    model(**VALID_KWARGS[model])  # valid baseline constructs
    with pytest.raises(ValidationError):
        model(**{**VALID_KWARGS[model], "definitely_not_a_field": 1})


def test_strict_rejects_type_coercion():
    with pytest.raises(ValidationError):
        ScoreWeights(concept_match="35")  # str -> float
    with pytest.raises(ValidationError):
        LineRange(start="1", end="2")  # str -> int
    with pytest.raises(ValidationError):
        ExecutionConfig(run_tests="true")  # str -> bool
    with pytest.raises(ValidationError):
        MetricsConfig(beta="1.0")


def test_defaults_are_validated_and_valid():
    assert ScoreWeights().total() == 100.0
    assert CaseInput().after_dir == "after"
    assert ScoringConfig().false_positive_penalty == 5
    assert MetricsConfig().beta == 1.0


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_numbers_rejected(bad):
    with pytest.raises(ValidationError):
        MetricsConfig(beta=bad)
    with pytest.raises(ValidationError):
        ScoringConfig(false_positive_penalty=bad)
    with pytest.raises(ValidationError):
        Finding(**_finding(confidence=bad))


def test_numeric_safety_bounds():
    with pytest.raises(ValidationError):
        MetricsConfig(beta=0)  # gt=0
    with pytest.raises(ValidationError):
        LineRange(start=5, end=3)  # end before start
    with pytest.raises(ValidationError):
        LineRange(start=1, end=limits.LINE_NUMBER_MAX + 1)  # magnitude cap
    with pytest.raises(ValidationError):
        Finding(**_finding(confidence=1.5))  # le=1
    with pytest.raises(ValidationError):
        ValidationConfig(max_false_positives=-1)


def test_collection_bounds_at_and_over_limit():
    files = [{"path": "a.py", "line_ranges": [{"start": 1, "end": 1}]}]
    # concepts exactly at the cap is accepted; one over is rejected.
    GroundTruthBug(summary="s", files=files, concepts=["c"] * limits.CONCEPTS_PER_BUG)
    with pytest.raises(ValidationError):
        GroundTruthBug(summary="s", files=files, concepts=["c"] * (limits.CONCEPTS_PER_BUG + 1))
    # findings list cap on reviewer output
    ReviewResult(
        findings=[Finding(**_finding())] * limits.FINDINGS_PER_RESPONSE,
        overall_risk="low",
        review_summary="x",
    )
    with pytest.raises(ValidationError):
        ReviewResult(
            findings=[Finding(**_finding())] * (limits.FINDINGS_PER_RESPONSE + 1),
            overall_risk="low",
            review_summary="x",
        )


def test_string_length_at_and_over_limit():
    files = [{"path": "a.py", "line_ranges": [{"start": 1, "end": 1}]}]
    GroundTruthBug(summary="x" * limits.SUMMARY_LEN, files=files, concepts=["c"])
    with pytest.raises(ValidationError):
        GroundTruthBug(summary="x" * (limits.SUMMARY_LEN + 1), files=files, concepts=["c"])


def test_empty_required_strings_and_collections_rejected():
    files = [{"path": "a.py", "line_ranges": [{"start": 1, "end": 1}]}]
    with pytest.raises(ValidationError):
        GroundTruthBug(summary="", files=files, concepts=["c"])  # empty summary
    with pytest.raises(ValidationError):
        GroundTruthBug(summary="s", files=files, concepts=[])  # empty concepts
    with pytest.raises(ValidationError):
        GroundTruthBug(summary="s", files=[], concepts=["c"])  # empty files


def test_validation_config_rejects_duplicate_collections():
    ValidationConfig(protected_paths=["tests", "conftest.py"])  # distinct ok
    with pytest.raises(ValidationError):
        ValidationConfig(protected_paths=["tests", "tests"])
    with pytest.raises(ValidationError):
        ValidationConfig(structural_validators=["v", "v"])


def test_create_run_request_strict_and_bounded():
    CreateRunRequest()  # defaults valid
    with pytest.raises(ValidationError):
        CreateRunRequest(allow_local_execution="true")  # str -> bool
    with pytest.raises(ValidationError):
        CreateRunRequest(beta="1.0")  # str -> float
    with pytest.raises(ValidationError):
        CreateRunRequest(beta=float("nan"))
    with pytest.raises(ValidationError):
        CreateRunRequest(max_cost=-1)  # negative cost
    with pytest.raises(ValidationError):
        CreateRunRequest(max_wall_seconds=0)  # must be positive when supplied
    with pytest.raises(ValidationError):
        CreateRunRequest(unknown_field=1)  # forbid extra
