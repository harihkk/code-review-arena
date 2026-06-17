"""v2 storage: new run-validity columns persist and gate the API leaderboard."""

from datetime import datetime

from arena.core.models import DeterministicMetrics, RunMetadata, RunResult
from arena.storage.repository import RunRepository


def _metrics(case_rate: float) -> DeterministicMetrics:
    return DeterministicMetrics(
        beta=1.0,
        false_positives_per_case=0.0,
        latency_per_case_ms=0.0,
        validated_case_rate=case_rate,
        validated_f_beta=case_rate,
        deterministic_pass_rate=case_rate,
    )


def _run(run_id: str, model: str, *, status: str, schema: int = 2, case_rate: float = 1.0):
    return RunResult(
        run_id=run_id,
        benchmark_set="v1",
        reviewer="control",
        model=model,
        started_at=datetime.now(),
        completed_at=datetime.now(),
        metadata=RunMetadata(prompt_version="v1", benchmark_version="v1"),
        case_results=[],
        total_score=0.0,
        schema_version=schema,
        run_status=status,  # type: ignore[arg-type]
        execution_backend="trusted-local",
        mode="full",
        deterministic_metrics=_metrics(case_rate),
        bugs_found=0,
        correct_files=0,
        correct_lines=0,
        false_positives=0,
        total_cost=0.0,
        total_latency_ms=0,
    )


def test_get_round_trips_v2_run_fields(tmp_path):
    repo = RunRepository(tmp_path / "arena.db")
    repo.save(_run("c1", "perfect", status="complete"))
    got = repo.get("c1")
    assert got is not None
    assert got.schema_version == 2
    assert got.run_status == "complete"
    assert got.execution_backend == "trusted-local"
    assert got.deterministic_metrics is not None
    assert got.deterministic_metrics.validated_case_rate == 1.0


def test_repository_leaderboard_excludes_partial_and_legacy(tmp_path):
    repo = RunRepository(tmp_path / "arena.db")
    repo.save(_run("c1", "perfect", status="complete", case_rate=1.0))
    repo.save(_run("p1", "flaky", status="partial", case_rate=0.5))
    repo.save(_run("l1", "old", status="complete", schema=1, case_rate=1.0))
    board = repo.leaderboard()
    assert {row["model"] for row in board} == {"perfect"}
