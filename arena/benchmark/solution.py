"""Materialize the corrected solution for a case.

Benchmark convention: ``after/`` is the buggy pull-request state and
``reference.patch`` is the canonical fix applied on top of it (the same patch the
runner applies the reviewer's repair against). So the *correct* solution is
``after/`` with ``reference.patch`` applied, not ``after/`` itself. Mutation
testing and certification both need that corrected tree to be meaningful.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from arena.benchmark.artifacts import load_reference_patch
from arena.core.models import BenchmarkCase
from arena.reviewers.reference_patch import REFERENCE_PATCH_FILENAME


@contextmanager
def fixed_solution(case: BenchmarkCase) -> Iterator[Path | None]:
    """Yield a temp dir holding ``after/`` with ``reference.patch`` applied.

    If the case ships no reference patch, ``after/`` is used as-is (it is already
    the intended solution). Yields ``None`` if a reference patch exists but does
    not apply cleanly, so callers can treat the case as uncertifiable.
    """
    assert case.case_dir is not None
    after_dir = case.case_dir / case.input.after_dir
    reference = case.case_dir / REFERENCE_PATCH_FILENAME
    with tempfile.TemporaryDirectory(prefix=f"arena-fixed-{case.id}-") as directory:
        workspace = Path(directory)
        shutil.copytree(after_dir, workspace, dirs_exist_ok=True)
        if reference.is_file():
            patch_file = workspace / ".arena-reference.patch"
            patch_file.write_text(load_reference_patch(reference), encoding="utf-8")
            applied = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(patch_file.resolve())],
                cwd=workspace,
                capture_output=True,
                text=True,
                check=False,
            )
            patch_file.unlink(missing_ok=True)
            if applied.returncode != 0:
                yield None
                return
        yield workspace
