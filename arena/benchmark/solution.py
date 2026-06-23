"""Materialize the corrected solution for a case.

Benchmark convention: ``after/`` is the buggy pull-request state and
``reference.patch`` is the canonical fix applied on top of it (the same patch the
runner applies the reviewer's repair against). So the *correct* solution is
``after/`` with ``reference.patch`` applied, not ``after/`` itself. Mutation
testing and certification both need that corrected tree to be meaningful.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from arena.benchmark.artifacts import load_reference_patch
from arena.core.models import BenchmarkCase
from arena.patching.git_pipeline import apply_patch
from arena.reviewers.reference_patch import REFERENCE_PATCH_FILENAME


@contextmanager
def fixed_solution(case: BenchmarkCase) -> Iterator[Path | None]:
    """Yield a temp dir holding ``after/`` with ``reference.patch`` applied.

    The reference patch goes through the SAME Git-authoritative pipeline and policy
    as a candidate patch (no special trust): a reference patch that fails to apply
    cleanly or violates the safety policy makes the case uncertifiable. If the case
    ships no reference patch, ``after/`` is used as-is. Yields ``None`` when the
    reference patch exists but does not apply or is rejected.
    """
    assert case.case_dir is not None
    after_dir = case.case_dir / case.input.after_dir
    reference = case.case_dir / REFERENCE_PATCH_FILENAME
    with tempfile.TemporaryDirectory(prefix=f"arena-fixed-{case.id}-") as directory:
        workspace = Path(directory) / "solution"
        if not reference.is_file():
            # No reference patch: after/ is already the intended solution.
            shutil.copytree(after_dir, workspace, symlinks=True)
            yield workspace
            return
        protected = list(case.validation.protected_paths)
        if case.input.tests_dir:
            protected.append(case.input.tests_dir)
        result = apply_patch(
            source_dir=after_dir,
            patch_text=load_reference_patch(reference),
            protected_paths=protected,
            destination=workspace,
        )
        if not result.applied:
            yield None
            return
        yield result.workspace
