from pathlib import Path
from typing import Literal

from rich.console import Console

from arena.benchmark.benchmark_runner import run_benchmark
from arena.core.registry import create_reviewer


def run(
    benchmark_set: Path,
    reviewer_spec: str,
    model: str | None,
    models: str | None,
    mode: Literal["review", "patch", "full"],
    beta: float | None,
    allow_local_execution: bool,
    command: str | None,
    reviewer_timeout_seconds: int,
) -> None:
    reviewer = create_reviewer(
        reviewer_spec,
        model=model,
        models=models,
        command=command,
        reviewer_timeout_seconds=reviewer_timeout_seconds,
    )
    result = run_benchmark(
        benchmark_set,
        reviewer,
        mode=mode,
        beta=beta,
        allow_local_execution=allow_local_execution,
    )
    Console().print(
        f"[green]Completed[/green] {result.run_id}: review_quality_score={result.total_score:.1f}, "
        f"bugs={result.bugs_found}/{result.case_count}, false_positives={result.false_positives}"
    )
    if result.deterministic_metrics:
        metrics = result.deterministic_metrics
        deterministic_passes = sum(item.deterministic_pass is True for item in result.case_results)
        Console().print(f"Detection: detection_f_beta={metrics.detection_f_beta:.3f}")
        Console().print(
            f"Validation: passes={deterministic_passes}/{result.case_count}, "
            f"validated_f_beta={metrics.validated_f_beta:.3f}, "
            f"deterministic_pass_rate={_format_rate(metrics.deterministic_pass_rate)}, "
            f"patch_apply_rate={_format_rate(metrics.patch_apply_rate)}, "
            f"structural_pass_rate={_format_rate(metrics.structural_pass_rate)}"
        )
    Console().print(f"Reports: runs/{result.run_id}/")


def _format_rate(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"
