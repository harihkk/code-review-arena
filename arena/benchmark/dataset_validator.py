"""Validation for benchmark files, paths and ground truth localization."""

from __future__ import annotations

from pathlib import Path

from arena.benchmark.case_loader import load_cases
from arena.benchmark.diff_loader import load_diff, parse_added_lines
from arena.core.errors import ValidationError
from arena.core.models import BenchmarkCase


def validate_case(case: BenchmarkCase) -> list[str]:
    errors: list[str] = []
    assert case.case_dir is not None
    before_dir = case.case_dir / case.input.before_dir
    after_dir = case.case_dir / case.input.after_dir
    if not before_dir.is_dir():
        errors.append(f"{case.id}: missing before directory")
    if not after_dir.is_dir():
        errors.append(f"{case.id}: missing after directory")
    try:
        changed = parse_added_lines(load_diff(case.case_dir / case.input.diff))
        if not changed:
            errors.append(f"{case.id}: diff contains no added lines")
    except ValidationError as exc:
        errors.append(str(exc))
    if case.scoring.weights.total() != 100:
        errors.append(f"{case.id}: scoring weights must sum to 100")
    if case.execution.run_tests and not case.execution.test_command:
        errors.append(f"{case.id}: test_command is required when run_tests is enabled")
    for expected_file in case.ground_truth.primary_bug.files:
        path = after_dir / expected_file.path
        if not path.is_file():
            errors.append(f"{case.id}: ground truth file not found: {expected_file.path}")
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        for line_range in expected_file.line_ranges:
            if line_range.end > line_count:
                errors.append(
                    f"{case.id}: line range {line_range.start}-{line_range.end} "
                    f"exceeds {expected_file.path} ({line_count} lines)"
                )
    return errors


def validate_dataset(benchmark_dir: Path) -> list[str]:
    try:
        cases = load_cases(benchmark_dir)
    except ValidationError as exc:
        return [str(exc)]
    errors: list[str] = []
    for case in cases:
        errors.extend(validate_case(case))
    if not cases:
        errors.append("Benchmark contains no cases")
    return errors
