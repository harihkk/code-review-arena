from arena.benchmark.case_loader import build_context, load_cases
from arena.reviewers.mock import MockReviewer
from arena.scoring.line_matcher import normalize_path, path_matches
from arena.scoring.scorer import score_case


def _case(benchmark_dir):
    return load_cases(benchmark_dir)[0]


def test_normalized_file_matching():
    assert normalize_path("./b/app/routes/admin.py") == "app/routes/admin.py"
    assert path_matches("b/app/routes/admin.py", "app/routes/admin.py")


def test_perfect_mock_scores_full_points(benchmark_dir):
    case = _case(benchmark_dir)
    result = score_case(case, MockReviewer("perfect").review(build_context(case)))
    assert result.score == 100
    assert result.correct_line is True


def test_false_positive_is_penalized(benchmark_dir):
    case = _case(benchmark_dir)
    result = score_case(case, MockReviewer("false-positive").review(build_context(case)))
    assert result.score == 90
    assert result.false_positive_count == 1
    assert result.scored_findings[1].false_positive_reason == "style-only"


def test_invalid_output_scores_zero(benchmark_dir):
    case = _case(benchmark_dir)
    result = score_case(case, MockReviewer("invalid_json").review(build_context(case)))
    assert result.score == 0
    assert result.response.invalid_output
