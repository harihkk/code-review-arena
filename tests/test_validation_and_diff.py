from arena.benchmark.case_loader import load_cases
from arena.benchmark.dataset_validator import validate_dataset
from arena.benchmark.diff_loader import load_diff, parse_added_lines


def test_dataset_is_valid(benchmark_dir):
    assert validate_dataset(benchmark_dir) == []


def test_diff_maps_added_after_lines(benchmark_dir):
    case = [item for item in load_cases(benchmark_dir) if item.id == "api_contract_regression_001"][
        0
    ]
    lines = parse_added_lines(load_diff(case.case_dir / case.input.diff))
    assert {3, 4, 5}.issubset(lines["app/routes/profile.py"])
