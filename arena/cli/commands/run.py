from pathlib import Path
from typing import Literal

import typer
from rich.console import Console

from arena.benchmark.benchmark_runner import run_benchmark
from arena.core.config import runs_path
from arena.core.errors import ArenaError
from arena.core.registry import create_reviewer


def run(
    benchmark_set: Path,
    reviewer_spec: str,
    mode: Literal["review", "patch", "full"],
    beta: float | None,
    allow_local_execution: bool,
    command: str | None,
    reviewer_timeout_seconds: int,
    as_json: bool = False,
    reveal_metadata: bool = False,
    enable_repair: bool = False,
    max_wall_seconds: float | None = None,
    max_cost: float | None = None,
) -> None:
    try:
        reviewer = create_reviewer(
            reviewer_spec,
            command=command,
            reviewer_timeout_seconds=reviewer_timeout_seconds,
            reveal_metadata=reveal_metadata,
            enable_repair=enable_repair,
        )
        result = run_benchmark(
            benchmark_set,
            reviewer,
            mode=mode,
            beta=beta,
            allow_local_execution=allow_local_execution,
            max_wall_seconds=max_wall_seconds,
            max_cost=max_cost,
        )
    except ArenaError as exc:
        Console(stderr=True).print(f"[red]ERROR[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if result.budget_stopped_reason:
        Console(stderr=True).print(
            f"[yellow]Stopped early[/yellow] {result.budget_stopped_reason}; "
            f"skipped {len(result.skipped_case_ids)} case(s). Partial results recorded."
        )
    if result.metadata.pack_checksum_verified is False:
        Console(stderr=True).print(
            "[yellow]WARNING[/yellow] benchmark pack content does not match its stored "
            "pack.sha256; results may come from a tampered pack."
        )
    if as_json:
        typer.echo(result.model_dump_json(indent=2))
        return

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
    Console().print(f"Reports: {runs_path() / result.run_id}/")


def _format_rate(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"
