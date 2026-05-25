"""Command-line application for CodeReview Arena."""

from pathlib import Path
from typing import Literal

import typer

from arena.cli.commands.audit_report import audit_report as audit_report_command
from arena.cli.commands.leaderboard import leaderboard as leaderboard_command
from arena.cli.commands.list_cases import list_cases as list_cases_command
from arena.cli.commands.report import report as report_command
from arena.cli.commands.run import run as run_command
from arena.cli.commands.validate import validate as validate_command
from arena.core.config import DEFAULT_BENCHMARK_SET, DEFAULT_RUNS_DIR

app = typer.Typer(help="Benchmark AI code reviewers on realistic pull-request bugs.")


@app.command("list-cases")
def list_cases(benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET)) -> None:
    list_cases_command(benchmark_set)


@app.command()
def validate(benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET)) -> None:
    validate_command(benchmark_set)


@app.command()
def run(
    benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET),
    reviewer: str = typer.Option("mock:perfect", "--reviewer"),
    model: str | None = typer.Option(None, "--model"),
    models: str | None = typer.Option(None, "--models"),
    mode: Literal["review", "patch", "full"] = typer.Option("review", "--mode"),
    beta: float | None = typer.Option(None, "--beta", min=0.01),
    allow_local_execution: bool = typer.Option(False, "--allow-local-execution"),
    command: str | None = typer.Option(None, "--command"),
    reviewer_timeout_seconds: int = typer.Option(120, "--reviewer-timeout-seconds", min=1),
) -> None:
    run_command(
        benchmark_set,
        reviewer,
        model,
        models,
        mode,
        beta,
        allow_local_execution,
        command,
        reviewer_timeout_seconds,
    )


@app.command()
def report(
    run_path: Path = typer.Argument(...),
    format: str = typer.Option("markdown", "--format"),
) -> None:
    report_command(run_path, format)


@app.command("audit-report")
def audit_report(
    runs_dir: Path = typer.Argument(DEFAULT_RUNS_DIR),
    output: Path = typer.Option(
        Path("docs/reports/audit-v1-results.md"),
        "--output",
    ),
    json_output: Path | None = typer.Option(
        Path("dashboard/public/reports/audit-v1.json"),
        "--json-output",
    ),
) -> None:
    audit_report_command(runs_dir, output, json_output)


@app.command()
def leaderboard(
    runs_dir: Path = typer.Argument(DEFAULT_RUNS_DIR),
    metric: str = typer.Option("validated_f_beta", "--metric"),
    beta: float = typer.Option(1.0, "--beta", min=0.01),
) -> None:
    leaderboard_command(runs_dir, metric, beta)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    import uvicorn

    uvicorn.run("arena.server.main:app", host=host, port=port)


if __name__ == "__main__":
    app()
