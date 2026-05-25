"""Temporary materialization for case-local execution."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from arena.core.models import BenchmarkCase


@contextmanager
def materialized_case(case: BenchmarkCase) -> Iterator[Path]:
    assert case.case_dir is not None
    with tempfile.TemporaryDirectory(prefix=f"arena-{case.id}-") as directory:
        root = Path(directory)
        shutil.copytree(case.case_dir / case.input.after_dir, root, dirs_exist_ok=True)
        tests = case.case_dir / (case.input.tests_dir or "tests")
        if case.input.tests_dir and tests.is_dir():
            shutil.copytree(tests, root / "tests", dirs_exist_ok=True)
        yield root
