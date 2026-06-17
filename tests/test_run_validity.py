"""Run trust level: status, coverage, and leaderboard eligibility."""

from datetime import datetime
from pathlib import Path
from time import monotonic

from arena.benchmark.benchmark_runner import _effective_timeout, _run_status, run_benchmark
from arena.core.models import RUN_SCHEMA_VERSION, RunMetadata, RunResult
from arena.reports.leaderboard import leaderboard_eligible, leaderboard_rows
from arena.reviewers.controls import ControlReviewer

V1 = Path("benchmark_sets/v1")


def _minimal_run(**overrides) -> RunResult:
    base = dict(
        run_id="r",
        benchmark_set="v1",
        reviewer="control",
        model="perfect",
        started_at=datetime.now(),
        completed_at=datetime.now(),
        metadata=RunMetadata(prompt_version="v1", benchmark_version="v1"),
        case_results=[],
        total_score=0.0,
        bugs_found=0,
        correct_files=0,
        correct_lines=0,
        false_positives=0,
        total_cost=0.0,
        total_latency_ms=0,
    )
    base.update(overrides)
    return RunResult(**base)


def test_effective_timeout_clamps_to_the_run_deadline():
    # No deadline: the case timeout is used as-is.
    assert _effective_timeout(30, None) == 30
    # A near deadline shortens the per-case timeout.
    soon = _effective_timeout(30, monotonic() + 5)
    assert 1 <= soon <= 5
    # Past the deadline, it floors at 1s rather than going negative.
    assert _effective_timeout(30, monotonic() - 10) == 1


def test_run_status_classifies_each_trust_level():
    assert _run_status(results=10, skipped=False, checksum_verified=None) == "complete"
    assert _run_status(results=10, skipped=False, checksum_verified=True) == "complete"
    assert _run_status(results=3, skipped=True, checksum_verified=None) == "partial"
    # A budget that trips before any case runs is still a truncation, not a crash.
    assert _run_status(results=0, skipped=True, checksum_verified=None) == "partial"
    assert _run_status(results=0, skipped=False, checksum_verified=None) == "failed"
    # A tampered pack invalidates the whole run regardless of coverage.
    assert _run_status(results=10, skipped=True, checksum_verified=False) == "invalid"


def test_execution_backend_reflects_actual_execution(tmp_path):
    full = run_benchmark(
        V1,
        ControlReviewer("perfect_patch"),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="full",
        allow_local_execution=True,
    )
    assert full.execution_backend == "trusted-local"
    assert any(case.execution_backend == "trusted-local" for case in full.case_results)

    review = run_benchmark(
        V1, ControlReviewer("perfect"), output_dir=tmp_path / "review-runs", persist=False
    )
    assert review.execution_backend == "none"


def test_complete_run_records_full_coverage(tmp_path):
    run = run_benchmark(V1, ControlReviewer("perfect"), output_dir=tmp_path / "runs", persist=False)
    assert run.schema_version == RUN_SCHEMA_VERSION
    assert run.run_status == "complete"
    assert run.execution_backend == "none"  # review mode never executes
    assert run.skipped_case_count == 0
    assert run.failed_case_count == 0
    assert run.eligible_case_count == run.completed_case_count == run.case_count
    assert run.coverage_rate == 1.0


def test_leaderboard_includes_complete_and_excludes_partial(tmp_path):
    runs_dir = tmp_path / "runs"
    complete = run_benchmark(V1, ControlReviewer("perfect"), output_dir=runs_dir, persist=False)
    partial = run_benchmark(
        V1, ControlReviewer("perfect"), output_dir=runs_dir, persist=False, max_wall_seconds=0.0
    )
    assert complete.run_status == "complete"
    assert partial.run_status == "partial"
    run_ids = {row["run_id"] for row in leaderboard_rows(runs_dir)}
    assert complete.run_id in run_ids
    assert partial.run_id not in run_ids


def test_leaderboard_eligibility_rules():
    assert leaderboard_eligible(_minimal_run(schema_version=2, run_status="complete")) is True
    # Pre-v2 runs are legacy even when complete.
    assert leaderboard_eligible(_minimal_run(schema_version=1, run_status="complete")) is False
    for status in ("partial", "invalid", "failed", "cancelled", "legacy"):
        assert leaderboard_eligible(_minimal_run(schema_version=2, run_status=status)) is False
    # Trusted-local runs are unverified: excluded by default, included on opt-in.
    local = _minimal_run(schema_version=2, run_status="complete", execution_backend="trusted-local")
    assert leaderboard_eligible(local) is False
    assert leaderboard_eligible(local, include_unverified=True) is True
