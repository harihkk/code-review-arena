import json

from arena.benchmark.case_loader import build_context, load_cases
from arena.reviewers.mock import MockReviewer
from arena.reviewers.response_parser import parse_review_response


def test_tolerant_parser_accepts_fenced_json(benchmark_dir):
    case = load_cases(benchmark_dir)[0]
    raw = MockReviewer().review(build_context(case)).raw_response
    parsed, attempts = parse_review_response(f"```json\n{raw}\n```")
    assert parsed is not None
    assert attempts == 2


def test_mock_partial_is_valid_structured_json(benchmark_dir):
    case = load_cases(benchmark_dir)[0]
    response = MockReviewer("partial").review(build_context(case))
    assert json.loads(response.raw_response)["findings"]
    assert response.parsed_response is not None
