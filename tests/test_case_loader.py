from arena.benchmark.case_loader import build_context, load_cases
from arena.benchmark.ground_truth import reviewer_safe_metadata


def test_loads_ten_cases(benchmark_dir):
    cases = load_cases(benchmark_dir)
    assert len(cases) == 10
    assert cases[0].id == "fastapi_auth_bypass_001"


def test_context_has_diff_and_files_but_metadata_helper_hides_answer(benchmark_dir):
    case = load_cases(benchmark_dir)[0]
    context = build_context(case)
    assert "delete_user" in context.diff
    assert "app/routes/admin.py" in context.relevant_files
    assert not hasattr(context.case, "ground_truth")
    assert "ground_truth" not in reviewer_safe_metadata(case)
