import json

from arena.benchmark.case_loader import build_context, load_cases
from arena.reviewers.controls import ControlReviewer
from arena.reviewers.response_parser import parse_reviewer_output

_VALID = {"findings": [], "overall_risk": "none", "review_summary": "x"}


def test_fenced_json_is_invalid_by_default_and_tolerant_only_with_salvage():
    raw = json.dumps(_VALID)
    fenced = f"```json\n{raw}\n```"
    # Exact-by-default: a Markdown fence makes the response invalid.
    assert parse_reviewer_output(fenced).status == "invalid"
    # Development salvage strips the fence and records it as a tolerant transform.
    outcome = parse_reviewer_output(fenced, enable_repair=True)
    assert outcome.status == "tolerant"
    assert outcome.attempt_count == 2
    assert outcome.actions == ["strip_markdown_fence"]
    assert outcome.result is not None


def test_mock_partial_is_valid_structured_json(benchmark_dir):
    case = load_cases(benchmark_dir)[0]
    response = ControlReviewer("partial").review(build_context(case))
    assert json.loads(response.raw_response)["findings"]
    assert response.parsed_response is not None
    # Built-in controls emit exact output (no salvage, no dropped findings).
    assert response.parse_status == "exact"
    assert response.dropped_finding_count == 0
