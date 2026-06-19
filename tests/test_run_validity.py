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


def _status(**overrides) -> str:
    base = dict(
        results=10,
        skipped=False,
        checksum_verified=None,
        execution_required=False,
        executed=0,
        unavailable=0,
    )
    base.update(overrides)
    return _run_status(**base)


def test_run_status_classifies_each_trust_level():
    assert _status() == "complete"
    assert _status(checksum_verified=True) == "complete"
    assert _status(results=3, skipped=True) == "partial"
    # A budget that trips before any case runs is still a truncation, not a crash.
    assert _status(results=0, skipped=True) == "partial"
    assert _status(results=0) == "failed"
    # A tampered pack invalidates the whole run regardless of coverage.
    assert _status(skipped=True, checksum_verified=False) == "invalid"


def test_run_status_invalid_when_execution_required_but_backend_unavailable():
    # Execution was required, nothing ran, and cases tried: scores are not real.
    assert _status(execution_required=True, executed=0, unavailable=5, results=5) == "invalid"
    # A review-mode run never needs execution, so an unavailable backend is moot.
    assert _status(execution_required=False, executed=0, unavailable=5) == "complete"
    # Some cases ran and some could not: partial, not invalid.
    assert _status(execution_required=True, executed=3, unavailable=2) == "partial"
    # Execution required but every case ran: complete.
    assert _status(execution_required=True, executed=10, unavailable=0) == "complete"


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


def test_full_run_is_invalid_when_no_execution_backend_is_available(tmp_path):
    # Full mode needs test execution, but local execution is off and the V1 cases
    # ship no docker image: nothing can run, so no repair can be judged and the
    # scores are not a fair measurement of the reviewer.
    run = run_benchmark(
        V1,
        ControlReviewer("perfect_patch"),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="full",
        allow_local_execution=False,
    )
    assert run.run_status == "invalid"
    assert run.execution_backend == "none"
    # Every case that applied a patch tried to run and hit the disabled backend.
    assert any(case.execution_unavailable for case in run.case_results)
    assert leaderboard_eligible(run) is False


def test_local_execution_requires_a_trusted_pack_hash(tmp_path, monkeypatch):
    import warnings

    from arena.benchmark.pack_hash import pack_checksum

    # An allowlist that does not include this pack's checksum blocks host execution
    # even though --allow-local-execution was passed: nothing runs, so the run is
    # invalid rather than silently trusting an unlisted pack.
    monkeypatch.setenv("ARENA_TRUSTED_PACK_HASHES", "0000deadbeef")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        blocked = run_benchmark(
            V1,
            ControlReviewer("perfect_patch"),
            output_dir=tmp_path / "blocked",
            persist=False,
            mode="full",
            allow_local_execution=True,
        )
    assert blocked.execution_backend == "none"
    assert blocked.run_status == "invalid"

    # The pack's real checksum on the allowlist permits local execution.
    monkeypatch.setenv("ARENA_TRUSTED_PACK_HASHES", pack_checksum(V1))
    allowed = run_benchmark(
        V1,
        ControlReviewer("perfect_patch"),
        output_dir=tmp_path / "allowed",
        persist=False,
        mode="full",
        allow_local_execution=True,
    )
    assert allowed.execution_backend == "trusted-local"
    assert allowed.run_status == "complete"


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
