import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from arena.reports.leaderboard import leaderboard_rows


def leaderboard(
    runs_dir: Path,
    metric: str = "validated_f_beta",
    beta: float = 1.0,
    as_json: bool = False,
) -> None:
    if not runs_dir.exists():
        Console(stderr=True).print(f"[red]ERROR[/red] runs directory not found: {runs_dir}")
        raise typer.Exit(code=1)
    try:
        rows = leaderboard_rows(runs_dir, metric=metric, beta=beta)
    except ValueError as exc:
        Console(stderr=True).print(f"[red]ERROR[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if as_json:
        typer.echo(json.dumps(rows, indent=2))
        return

    display_metric = "detection_f_beta" if metric == "f_beta" else metric
    table = Table()
    for column in [
        "Reviewer",
        "Model",
        display_metric,
        "Bugs Found",
        "False Positives",
        "Cost",
        "Latency",
    ]:
        table.add_column(column)
    for row in rows:
        table.add_row(
            str(row["reviewer"]),
            str(row["model"]),
            _metric_value(row["metric_value"], display_metric),
            str(row["bugs_found"]),
            str(row["false_positives"]),
            f"${row['cost']:.4f}",
            f"{row['latency_ms'] / 1000:.2f}s",
        )
    Console(width=140).print(table)


def _metric_value(value: float | None, metric: str) -> str:
    if value is None:
        return "n/a"
    if metric.endswith("_rate") or "_f_" in metric or metric.endswith(("_precision", "_recall")):
        return f"{value:.3f}"
    if metric == "cost_per_validated_fix":
        return f"${value:.4f}"
    return f"{value:.1f}"
