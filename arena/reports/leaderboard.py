"""Run report aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from arena.core.models import RunResult
from arena.reports.json_report import read_json_report
from arena.scoring.deterministic_scorer import aggregate_deterministic_metrics


class LeaderboardRow(TypedDict):
    reviewer: str
    model: str
    score: float
    bugs_found: str
    false_positives: int
    cost: float
    latency_ms: int
    run_id: str
    mode: str
    completed_at: str
    metric_value: float | None
    pack: str


def load_runs(runs_dir: Path) -> list[RunResult]:
    paths = sorted(runs_dir.glob("*/run.json"))
    return [read_json_report(path) for path in paths]


def leaderboard_rows(
    runs_dir: Path, metric: str = "validated_f_beta", beta: float = 1.0
) -> list[LeaderboardRow]:
    latest: dict[tuple[str, str | None, str], RunResult] = {}
    for run in load_runs(runs_dir):
        key = (run.reviewer, run.model, run.mode)
        previous = latest.get(key)
        if previous is None or run.completed_at > previous.completed_at:
            latest[key] = run
    rows: list[LeaderboardRow] = [
        {
            "reviewer": run.reviewer,
            "model": run.model or "",
            "score": run.total_score,
            "bugs_found": f"{run.bugs_found}/{run.case_count}",
            "false_positives": run.false_positives,
            "cost": run.total_cost,
            "latency_ms": run.total_latency_ms,
            "run_id": run.run_id,
            "mode": run.mode,
            "completed_at": run.completed_at.isoformat(),
            "metric_value": _metric(run, metric, beta),
            "pack": _pack_label(run),
        }
        for run in latest.values()
    ]
    descending = metric not in {
        "cost_per_validated_fix",
        "false_positives_per_case",
        "latency_per_case_ms",
    }
    return sorted(
        rows,
        key=lambda item: _sort_key(item["metric_value"], descending),
    )


def _pack_label(run: RunResult) -> str:
    checksum = run.metadata.pack_checksum
    if not checksum:
        return run.benchmark_set
    suffix = " (tampered!)" if run.metadata.pack_checksum_verified is False else ""
    return f"{run.benchmark_set}@{checksum[:10]}{suffix}"


def _sort_key(value: float | None, descending: bool) -> tuple[bool, float]:
    if value is None:
        return (True, 0.0)
    return (False, -value if descending else value)


def _metric(run: RunResult, metric: str, beta: float) -> float | None:
    if metric in {"score", "review_quality_score"}:
        return run.total_score
    if run.deterministic_metrics is None:
        return None
    metric = "detection_f_beta" if metric == "f_beta" else metric
    metrics = (
        aggregate_deterministic_metrics(
            run.case_results, beta, run.total_cost, run.total_latency_ms
        )
        if metric in {"detection_f_beta", "validated_f_beta"}
        else run.deterministic_metrics
    )
    valid = {
        "detection_f_beta",
        "detection_f1",
        "detection_precision",
        "detection_recall",
        "validated_f_beta",
        "validated_f1",
        "validated_precision",
        "validated_recall",
        "deterministic_pass_rate",
        "patch_apply_rate",
        "test_pass_rate",
        "structural_pass_rate",
        "false_positives_per_case",
        "cost_per_validated_fix",
        "latency_per_case_ms",
    }
    if metric not in valid:
        raise ValueError(f"Unsupported leaderboard metric: {metric}")
    values = {
        "detection_f_beta": metrics.detection_f_beta,
        "detection_f1": metrics.detection_f1,
        "detection_precision": metrics.detection_precision,
        "detection_recall": metrics.detection_recall,
        "validated_f_beta": metrics.validated_f_beta,
        "validated_f1": metrics.validated_f1,
        "validated_precision": metrics.validated_precision,
        "validated_recall": metrics.validated_recall,
        "deterministic_pass_rate": metrics.deterministic_pass_rate,
        "patch_apply_rate": metrics.patch_apply_rate,
        "test_pass_rate": metrics.test_pass_rate,
        "structural_pass_rate": metrics.structural_pass_rate,
        "false_positives_per_case": metrics.false_positives_per_case,
        "cost_per_validated_fix": metrics.cost_per_validated_fix,
        "latency_per_case_ms": metrics.latency_per_case_ms,
    }
    return values[metric]
