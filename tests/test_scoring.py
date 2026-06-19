from arena.benchmark.case_loader import build_context, load_cases
from arena.reviewers.controls import ControlReviewer
from arena.scoring.concept_matcher import mentions
from arena.scoring.line_matcher import normalize_path, path_matches
from arena.scoring.scorer import score_case


def test_concept_matching_is_word_bounded_and_ordered():
    # Legit phrases still match.
    assert mentions("this is a clear race condition", "race condition")
    assert mentions("guard the balance with a lock", "lock")
    assert mentions("scope it by tenant_id", "tenant_id")
    # Vocabulary stuffing must not: an unordered token bag does not earn a phrase,
    # and a substring inside another word does not match.
    assert not mentions("controls who can access the record", "access control")
    assert not mentions("the request was blocked", "lock")


def _case(benchmark_dir):
    return load_cases(benchmark_dir)[0]


def test_normalized_file_matching():
    assert normalize_path("./b/app/routes/admin.py") == "app/routes/admin.py"
    assert path_matches("b/app/routes/admin.py", "app/routes/admin.py")


def test_normalize_path_does_not_eat_leading_dots():
    # lstrip("./") would strip these leading dots as a character set, collapsing
    # distinct paths together. Only a single "./" prefix should be removed.
    assert normalize_path("../escape/x.py") == "../escape/x.py"
    assert normalize_path(".github/workflows/ci.yml") == ".github/workflows/ci.yml"
    assert not path_matches("../app/x.py", "app/x.py")
    assert not path_matches(".github/x.py", "github/x.py")
    # A real leading "./" or git a/ b/ prefix is still stripped.
    assert normalize_path("./app/x.py") == "app/x.py"
    assert normalize_path("a/app/x.py") == "app/x.py"


def test_perfect_control_scores_full_points(benchmark_dir):
    case = _case(benchmark_dir)
    result = score_case(case, ControlReviewer("perfect").review(build_context(case)))
    assert result.score == 100
    assert result.correct_line is True


def test_false_positive_is_penalized(benchmark_dir):
    case = _case(benchmark_dir)
    result = score_case(case, ControlReviewer("false-positive").review(build_context(case)))
    assert result.score == 90
    assert result.false_positive_count == 1
    assert result.scored_findings[1].false_positive_reason == "style-only"


def test_invalid_output_scores_zero(benchmark_dir):
    case = _case(benchmark_dir)
    result = score_case(case, ControlReviewer("invalid_json").review(build_context(case)))
    assert result.score == 0
    assert result.response.invalid_output
