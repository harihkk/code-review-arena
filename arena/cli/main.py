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
from arena.cli.commands.verify_reviewer import verify_reviewer as verify_reviewer_command
from arena.core.config import DEFAULT_BENCHMARK_SET, DEFAULT_RUNS_DIR, resolve_benchmark_path

app = typer.Typer(help="Benchmark AI code reviewers on realistic pull-request bugs.")


@app.command("list-cases")
def list_cases(benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET)) -> None:
    list_cases_command(resolve_benchmark_path(benchmark_set))


@app.command()
def validate(benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET)) -> None:
    validate_command(resolve_benchmark_path(benchmark_set))


@app.command()
def run(
    benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET),
    reviewer: str = typer.Option("mock:perfect", "--reviewer"),
    mode: Literal["review", "patch", "full"] = typer.Option("review", "--mode"),
    beta: float | None = typer.Option(None, "--beta", min=0.01),
    allow_local_execution: bool = typer.Option(False, "--allow-local-execution"),
    command: str | None = typer.Option(None, "--command"),
    reviewer_timeout_seconds: int = typer.Option(120, "--reviewer-timeout-seconds", min=1),
    reveal_metadata: bool = typer.Option(
        False,
        "--reveal-metadata",
        help="Include case title/description/category/severity in the reviewer payload. "
        "Debugging only: scored runs should stay blind.",
    ),
    enable_repair: bool = typer.Option(
        False,
        "--enable-repair",
        help="Attempt a deterministic salvage of malformed reviewer JSON "
        "(logged as parse_attempts=3) instead of taking the invalid-output penalty.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the run result as JSON to stdout."),
    max_wall_seconds: float | None = typer.Option(
        None,
        "--max-wall-seconds",
        min=0,
        help="Stop scheduling new cases once the run has taken this long.",
    ),
    max_cost: float | None = typer.Option(
        None,
        "--max-cost",
        min=0,
        help="Stop scheduling new cases once estimated reviewer cost reaches this budget.",
    ),
) -> None:
    run_command(
        resolve_benchmark_path(benchmark_set),
        reviewer,
        mode,
        beta,
        allow_local_execution,
        command,
        reviewer_timeout_seconds,
        as_json,
        reveal_metadata=reveal_metadata,
        enable_repair=enable_repair,
        max_wall_seconds=max_wall_seconds,
        max_cost=max_cost,
    )


@app.command()
def schema(
    output: Path | None = typer.Option(
        None, "--output", help="Write the schema to a file instead of stdout."
    ),
) -> None:
    """Emit the versioned JSON Schema a reviewer's output must satisfy."""
    import json

    from arena.core.config import REVIEW_SCHEMA_VERSION
    from arena.core.models import ReviewResult

    payload = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": (
            "https://github.com/harihkk/code-review-arena/"
            f"schema/review-result-{REVIEW_SCHEMA_VERSION}.json"
        ),
        "version": REVIEW_SCHEMA_VERSION,
        **ReviewResult.model_json_schema(),
    }
    rendered = json.dumps(payload, indent=2)
    if output is not None:
        output.write_text(rendered + "\n", encoding="utf-8")
        typer.echo(f"Wrote {output}")
    else:
        typer.echo(rendered)


@app.command("verify-reviewer")
def verify_reviewer(
    benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET),
    command: str = typer.Option(..., "--command", help="Wrapper command template to verify."),
    case_id: str | None = typer.Option(None, "--case-id"),
    reviewer_timeout_seconds: int = typer.Option(120, "--reviewer-timeout-seconds", min=1),
    reveal_metadata: bool = typer.Option(False, "--reveal-metadata"),
    enable_repair: bool = typer.Option(False, "--enable-repair"),
) -> None:
    """Run a wrapper against one case and validate its output with actionable errors."""
    verify_reviewer_command(
        resolve_benchmark_path(benchmark_set),
        command,
        case_id,
        reviewer_timeout_seconds,
        reveal_metadata,
        enable_repair,
    )


@app.command("pack-hash")
def pack_hash(
    benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET),
    write: bool = typer.Option(
        False, "--write", help="Store the checksum as pack.sha256 inside the pack."
    ),
) -> None:
    from arena.benchmark.pack_hash import pack_checksum, stored_checksum, write_checksum

    benchmark_set = resolve_benchmark_path(benchmark_set)
    checksum = write_checksum(benchmark_set) if write else pack_checksum(benchmark_set)
    typer.echo(checksum)
    pinned = stored_checksum(benchmark_set)
    if not write and pinned is not None and pinned != checksum:
        typer.echo(f"WARNING: pack content does not match stored pack.sha256 ({pinned})", err=True)
        raise typer.Exit(code=1)


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
    as_json: bool = typer.Option(False, "--json", help="Emit leaderboard rows as JSON to stdout."),
) -> None:
    leaderboard_command(runs_dir, metric, beta, as_json)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    import uvicorn

    uvicorn.run("arena.server.main:app", host=host, port=port)


if __name__ == "__main__":
    app()
