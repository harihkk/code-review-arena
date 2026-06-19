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
        tests_dir = case.input.tests_dir
        tests = case.case_dir / (tests_dir or "tests")
        if tests_dir and tests.is_dir():
            # Copy to the case's declared tests_dir, not a hardcoded "tests", so a
            # case whose test_command targets another directory still finds them.
            shutil.copytree(tests, root / tests_dir, dirs_exist_ok=True)
        yield root
