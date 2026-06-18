"""Evidence bundle: checksums seal a run dir and verify-run detects edits."""

import json
from pathlib import Path

from arena.benchmark.benchmark_runner import run_benchmark
from arena.reports.bundle import (
    CHECKSUMS_FILENAME,
    _sha256,
    verify_bundle,
    write_bundle_checksums,
)
from arena.reviewers.controls import ControlReviewer


def _seed(run_dir: Path) -> None:
    (run_dir / "run.json").write_text('{"run_id": "x"}', encoding="utf-8")
    (run_dir / "report.md").write_text("# report\n", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text('{"v": 1}', encoding="utf-8")


def test_fresh_bundle_verifies(tmp_path):
    _seed(tmp_path)
    identifier = write_bundle_checksums(tmp_path)
    result = verify_bundle(tmp_path)
    assert result.ok
    assert result.bundle_id == identifier


def test_modified_file_is_detected(tmp_path):
    _seed(tmp_path)
    write_bundle_checksums(tmp_path)
    (tmp_path / "run.json").write_text('{"run_id": "tampered"}', encoding="utf-8")
    result = verify_bundle(tmp_path)
    assert not result.ok
    assert "run.json" in result.modified


def test_missing_and_added_files_detected(tmp_path):
    _seed(tmp_path)
    write_bundle_checksums(tmp_path)
    (tmp_path / "report.md").unlink()
    (tmp_path / "extra.txt").write_text("sneaky", encoding="utf-8")
    result = verify_bundle(tmp_path)
    assert not result.ok
    assert "report.md" in result.missing
    assert "extra.txt" in result.added


def test_expected_id_pins_against_a_consistent_rewrite(tmp_path):
    _seed(tmp_path)
    real = write_bundle_checksums(tmp_path)
    assert verify_bundle(tmp_path, expected_id=real).ok
    mismatched = verify_bundle(tmp_path, expected_id="deadbeef")
    assert not mismatched.ok
    assert not mismatched.expected_id_ok


def test_missing_checksums_is_an_error(tmp_path):
    _seed(tmp_path)
    result = verify_bundle(tmp_path)
    assert not result.ok
    assert result.error


def test_internally_inconsistent_checksums_detected(tmp_path):
    _seed(tmp_path)
    write_bundle_checksums(tmp_path)
    # Edit a file and update its recorded hash, but leave the bundle_id stale:
    # the files now match the recorded map, yet the id no longer covers them.
    data = json.loads((tmp_path / CHECKSUMS_FILENAME).read_text(encoding="utf-8"))
    (tmp_path / "run.json").write_text('{"run_id": "tampered"}', encoding="utf-8")
    data["files"]["run.json"] = _sha256(tmp_path / "run.json")
    (tmp_path / CHECKSUMS_FILENAME).write_text(json.dumps(data), encoding="utf-8")
    result = verify_bundle(tmp_path)
    assert not result.ok
    assert not result.bundle_id_ok


def test_run_benchmark_writes_a_verifiable_bundle(tmp_path):
    run = run_benchmark(
        Path("benchmark_sets/v1"),
        ControlReviewer("perfect"),
        output_dir=tmp_path / "runs",
        persist=False,
    )
    run_dir = tmp_path / "runs" / run.run_id
    assert (run_dir / CHECKSUMS_FILENAME).exists()
    assert verify_bundle(run_dir).ok
