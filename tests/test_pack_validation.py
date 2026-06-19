"""Dataset validation must be a mandatory precondition for execution."""

from pathlib import Path

import pytest

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.dataset_validator import load_and_validate_pack
from arena.core.errors import ValidationError
from arena.reviewers.controls import ControlReviewer

VALID_PACK = Path("benchmark_sets/audit_v1")


def _write_invalid_pack(root: Path) -> Path:
    # Manifest references a case that has no directory on disk, so loading fails.
    pack = root / "invalid_pack"
    pack.mkdir()
    (pack / "manifest.yaml").write_text(
        "version: invalid_test\nname: invalid test pack\ncases:\n  - ghost_case\n",
        encoding="utf-8",
    )
    return pack


def test_load_and_validate_pack_accepts_a_valid_pack():
    # An existing, valid pack is unaffected: no new policy that rejects it.
    cases = load_and_validate_pack(VALID_PACK)
    assert len(cases) == 10


def test_load_and_validate_pack_rejects_invalid_pack(tmp_path):
    with pytest.raises(ValidationError):
        load_and_validate_pack(_write_invalid_pack(tmp_path))


def test_run_benchmark_aborts_invalid_pack_before_creating_run_dir(tmp_path):
    # The old code created the run directory, then loaded cases without
    # validating; an invalid pack must now abort before any side effect.
    runs_dir = tmp_path / "runs"
    with pytest.raises(ValidationError):
        run_benchmark(
            _write_invalid_pack(tmp_path),
            ControlReviewer("false_positive_patch"),
            output_dir=runs_dir,
            persist=False,
            mode="review",
        )
    assert not runs_dir.exists()
