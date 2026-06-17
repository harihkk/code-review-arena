"""Evidence attribution: per-finding status, per-bug repair, and case status."""

from arena.benchmark.benchmark_runner import _attribute_evidence
from arena.core.models import BenchmarkCase, Finding, ReviewerResponse, ReviewResult
from arena.execution.test_executor import TestExecutionResult
from arena.patching.patch_models import PatchApplyResult
from arena.scoring.deterministic_scorer import score_deterministic_case
from arena.scoring.scorer import score_case


def _case() -> BenchmarkCase:
    return BenchmarkCase.model_validate(
        {
            "id": "syn",
            "title": "t",
            "category": "correctness",
            "severity": "high",
            "stack": ["python"],
            "description": "d",
            "input": {},
            "ground_truth": {
                "bugs": [
                    {
                        "summary": "Race",
                        "files": [{"path": "app/a.py", "line_ranges": [{"start": 5, "end": 10}]}],
                        "concepts": ["race condition"],
                        "must_mention": ["lock"],
                        "acceptable_fix_keywords": ["lock"],
                    },
                    {
                        "summary": "SQLi",
                        "files": [{"path": "app/b.py", "line_ranges": [{"start": 1, "end": 3}]}],
                        "concepts": ["sql injection"],
                        "must_mention": ["parameterize"],
                        "acceptable_fix_keywords": ["bind"],
                    },
                ]
            },
        }
    )


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
    result = ReviewResult(findings=findings, overall_risk="high", review_summary="s")
    return ReviewerResponse(raw_response=result.model_dump_json(), parsed_response=result)


BUG0 = _finding("app/a.py", 5, 10, "Race condition needs a lock", "use a lock")
BUG1 = _finding("app/b.py", 1, 3, "SQL injection: parameterize", "use bind params")


def _deterministic(case, review, *, tests_passed: bool):
    patch = PatchApplyResult(
        case_id=case.id, applied=True, workspace_path="ws", patch_text="x", duration_ms=1
    )
    tests = TestExecutionResult(
        case_id=case.id, ran=True, passed=tests_passed, execution_mode="local"
    )
    return score_deterministic_case(case, review, patch, tests, [], beta=1.0)


def test_bug_ids_are_auto_assigned():
    case = _case()
    assert [bug.id for bug in case.ground_truth.bugs] == ["bug-1", "bug-2"]


def test_complete_repair_when_all_detected_and_validated():
    case = _case()
    review = score_case(case, _response([BUG0, BUG1]))
    det = _deterministic(case, review, tests_passed=True)
    bug_repairs, findings, status = _attribute_evidence(
        case, review, det, execution_validated=True, integrity_violated=False
    )
    assert status == "complete_repair"
    assert all(bug.detected and bug.repaired for bug in bug_repairs)
    assert {finding.evidence_status for finding in findings} == {"repair_validated"}


def test_detected_but_unrepaired_when_repair_fails():
    case = _case()
    review = score_case(case, _response([BUG0, BUG1]))
    det = _deterministic(case, review, tests_passed=False)
    bug_repairs, findings, status = _attribute_evidence(
        case, review, det, execution_validated=False, integrity_violated=False
    )
    assert status == "detected_but_unrepaired"
    assert all(bug.detected and not bug.repaired for bug in bug_repairs)
    assert {finding.evidence_status for finding in findings} == {"detected_but_unrepaired"}


def test_partial_repair_when_validated_but_detection_incomplete():
    case = _case()
    review = score_case(case, _response([BUG0]))  # only one of two bugs found
    det = _deterministic(case, review, tests_passed=True)
    bug_repairs, _, status = _attribute_evidence(
        case, review, det, execution_validated=True, integrity_violated=False
    )
    assert status == "partial_repair"
    assert sum(bug.detected for bug in bug_repairs) == 1


def test_unsupported_finding_is_flagged():
    case = _case()
    noise = _finding("unrelated/x.py", 1, 1, "style nit", "rename")
    review = score_case(case, _response([BUG0, BUG1, noise]))
    det = _deterministic(case, review, tests_passed=True)
    _, findings, _ = _attribute_evidence(
        case, review, det, execution_validated=True, integrity_violated=False
    )
    assert "unsupported" in {finding.evidence_status for finding in findings}


def test_tampering_overrides_case_status():
    case = _case()
    review = score_case(case, _response([BUG0, BUG1]))
    det = _deterministic(case, review, tests_passed=True)
    _, _, status = _attribute_evidence(
        case, review, det, execution_validated=False, integrity_violated=True
    )
    assert status == "tampering"
