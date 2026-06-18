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
    reviewer: str = typer.Option("control:perfect", "--reviewer"),
    mode: Literal["review", "patch", "full"] = typer.Option("review", "--mode"),
    beta: float | None = typer.Option(None, "--beta", min=0.01),
    allow_local_execution: bool = typer.Option(False, "--allow-local-execution"),
    command: str | None = typer.Option(None, "--command"),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Model name for openai:/http: reviewers (e.g. llama3). "
        "Falls back to ARENA_HTTP_MODEL.",
    ),
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
        model=model,
    )


@app.command("mutation-test")
def mutation_test(
    benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET),
    allow_local_execution: bool = typer.Option(False, "--allow-local-execution"),
    limit: int = typer.Option(20, "--limit", min=1, help="Max mutants per case."),
) -> None:
    """Mutate each case's solution and report how many mutants its tests kill."""
    from rich.console import Console

    from arena.benchmark.case_loader import load_cases
    from arena.benchmark.mutation import run_mutation_test

    console = Console()
    for case in load_cases(resolve_benchmark_path(benchmark_set)):
        if not case.execution.run_tests or not case.execution.test_command:
            console.print(f"{case.id}: skipped (no executable tests)")
            continue
        result = run_mutation_test(case, allow_local_execution=allow_local_execution, limit=limit)
        rate = f"{result.kill_rate:.0%}" if result.kill_rate is not None else "n/a"
        console.print(f"{case.id}: mutant_kill_rate={rate} ({result.killed}/{result.total})")


@app.command("verify-run")
def verify_run(
    run_dir: Path = typer.Argument(..., help="Path to a run directory (contains checksums.json)."),
    expected_id: str | None = typer.Option(
        None, "--expected-id", help="Out-of-band bundle id to pin against a consistent rewrite."
    ),
) -> None:
    """Verify a saved run's evidence bundle has not been edited since it was written."""
    from rich.console import Console

    from arena.reports.bundle import verify_bundle

    console = Console()
    result = verify_bundle(run_dir, expected_id=expected_id)
    if result.error:
        console.print(f"[red]ERROR[/red] {result.error}")
        raise typer.Exit(code=1)
    if result.ok:
        console.print(f"[green]VERIFIED[/green] evidence bundle {result.bundle_id}")
        return
    console.print("[red]TAMPERED[/red] evidence bundle integrity check failed")
    for name in result.modified:
        console.print(f"  modified: {name}")
    for name in result.missing:
        console.print(f"  missing:  {name}")
    for name in result.added:
        console.print(f"  added:    {name}")
    if not result.bundle_id_ok:
        console.print("  checksums.json is internally inconsistent")
    if not result.expected_id_ok:
        console.print(f"  bundle id does not match expected {expected_id}")
    raise typer.Exit(code=1)


@app.command("certify-pack")
def certify_pack(
    benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET),
    allow_local_execution: bool = typer.Option(False, "--allow-local-execution"),
    limit: int = typer.Option(20, "--limit", min=1, help="Max mutants per case."),
    determinism_runs: int = typer.Option(
        1,
        "--determinism-runs",
        min=1,
        help="Re-run gates this many times to earn 'verified'; 1 disables the check.",
    ),
    strict: str = typer.Option(
        "",
        "--strict",
        help="Exit nonzero unless the pack reaches this level (certified or verified).",
    ),
) -> None:
    """Grade each case on the draft/development/certified/verified ladder."""
    from rich.console import Console

    from arena.benchmark.certify import LEVELS
    from arena.benchmark.certify import certify_pack as run_certify

    if strict and strict not in LEVELS:
        raise typer.BadParameter(f"--strict must be one of {', '.join(LEVELS)}")

    console = Console()
    report = run_certify(
        resolve_benchmark_path(benchmark_set),
        allow_local_execution=allow_local_execution,
        mutation_limit=limit,
        determinism_runs=determinism_runs,
    )

    def mark(value: bool | None) -> str:
        return "n/a" if value is None else ("pass" if value else "FAIL")

    unexecuted = 0
    for case in report.cases:
        if not case.executable:
            console.print(f"{case.case_id}: draft (no executable tests)")
            continue
        if not case.executed:
            unexecuted += 1
            console.print(f"{case.case_id}: not executed (no available backend)")
            continue
        kill = "n/a" if case.mutant_kill_rate is None else f"{case.mutant_kill_rate:.0%}"
        determinism = (
            "" if case.deterministic is None else f" deterministic={mark(case.deterministic)}"
        )
        # No square brackets: rich would parse them as markup and hide them.
        console.print(
            f"{case.case_id}: {case.level.upper()}  "
            f"baseline_fails={mark(case.baseline_fails)} "
            f"reference_passes={mark(case.reference_passes)} "
            f"mutant_kill_rate={kill} ({case.mutant_total} mutants)"
            f"{determinism}"
        )
    if unexecuted:
        console.print(
            f"[yellow]{unexecuted} case(s) had no backend to run their tests.[/yellow] "
            "Pass --allow-local-execution, or build the pack's docker image "
            "(scripts/build_bench_image.sh) and set default_docker_image."
        )
    console.print(f"\nPack '{report.pack}' level: {report.level}")
    if strict and LEVELS.index(report.level) < LEVELS.index(strict):
        raise typer.Exit(code=1)


@app.command("lint-cases")
def lint_cases(
    benchmark_set: Path = typer.Argument(DEFAULT_BENCHMARK_SET),
    strict: bool = typer.Option(
        False, "--strict", help="Exit nonzero when any contamination is found."
    ),
) -> None:
    """Scan cases for ground-truth vocabulary leaking into reviewer-visible surfaces."""
    from arena.benchmark.contamination import scan_benchmark

    warnings = scan_benchmark(resolve_benchmark_path(benchmark_set))
    for warning in warnings:
        typer.echo(warning.render())
    if warnings:
        typer.echo(
            f"{len(warnings)} potential leak(s); leaked phrases hand reviewers the answer "
            "(test names appear in pre-patch test output).",
            err=True,
        )
        if strict:
            raise typer.Exit(code=1)
    else:
        typer.echo("No contamination found.")


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
    benchmark_set: str = typer.Option(
        "audit_v1", "--benchmark-set", help="Which pack's runs to aggregate."
    ),
) -> None:
    audit_report_command(runs_dir, output, json_output, benchmark_set)


@app.command()
def leaderboard(
    runs_dir: Path = typer.Argument(DEFAULT_RUNS_DIR),
    metric: str = typer.Option("validated_case_rate", "--metric"),
    beta: float = typer.Option(1.0, "--beta", min=0.01),
    as_json: bool = typer.Option(False, "--json", help="Emit leaderboard rows as JSON to stdout."),
    include_unverified: bool = typer.Option(
        False,
        "--include-unverified",
        help="Include trusted-local (non-Docker) runs, which are excluded by default.",
    ),
) -> None:
    leaderboard_command(runs_dir, metric, beta, as_json, include_unverified)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
) -> None:
    import uvicorn

    uvicorn.run("arena.server.main:app", host=host, port=port)


if __name__ == "__main__":
    app()
