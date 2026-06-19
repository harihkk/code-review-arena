"""Temporary materialization for case-local execution."""

from __future__ import annotations

import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from arena.core.errors import ValidationError
from arena.core.models import BenchmarkCase
from arena.execution.integrity import find_unsafe_files

# The directory walk inside copytree can surface EINTR when a signal arrives
# mid-copy (observed under load on macOS while a model run was in flight). A copy
# is idempotent with dirs_exist_ok, so retry a few times rather than losing the
# whole case to transient signal noise.
_COPY_RETRIES = 4
_COPY_BACKOFF_SECONDS = 0.1


def _copytree_resilient(src: Path, dst: Path) -> None:
    for attempt in range(_COPY_RETRIES):
        try:
            # symlinks=True copies links as links rather than following them into
            # host data; admission rejects symlinks, this is defense in depth.
            shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)
            return
        except InterruptedError:
            if attempt == _COPY_RETRIES - 1:
                raise
            time.sleep(_COPY_BACKOFF_SECONDS * (attempt + 1))


@contextmanager
def materialized_case(case: BenchmarkCase) -> Iterator[Path]:
    assert case.case_dir is not None
    with tempfile.TemporaryDirectory(prefix=f"arena-{case.id}-") as directory:
        root = Path(directory)
        _copytree_resilient(case.case_dir / case.input.after_dir, root)
        tests_dir = case.input.tests_dir
        tests = case.case_dir / (tests_dir or "tests")
        if tests_dir and tests.is_dir():
            # Copy to the case's declared tests_dir, not a hardcoded "tests", so a
            # case whose test_command targets another directory still finds them.
            _copytree_resilient(tests, root / tests_dir)
        # copytree preserves symlinks rather than following them; re-scan the
        # materialized workspace and refuse to execute if any symlink or special
        # file survived (a link the local test command could otherwise follow out
        # of the workspace at runtime).
        unsafe = find_unsafe_files(root)
        if unsafe:
            raise ValidationError(
                f"workspace for case {case.id} contains unsafe entries after copy: "
                f"{', '.join(unsafe)}"
            )
        yield root
