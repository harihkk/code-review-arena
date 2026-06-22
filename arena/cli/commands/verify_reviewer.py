"""Run a reviewer wrapper against one case and validate its output contract."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError as PydanticValidationError
from rich.console import Console

from arena.benchmark.case_loader import build_context
from arena.benchmark.snapshot import snapshot_pack
from arena.core.errors import ArenaError
from arena.core.models import ReviewResult
from arena.reviewers.custom_command import CustomCommandReviewer


def _diagnose(raw: str, console: Console) -> None:
    """Explain why raw output failed the ReviewResult contract."""
    if not raw.strip():
        console.print("  The command produced no output on stdout.")
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        console.print(f"  stdout is not JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}.")
        tail = raw.strip()[-300:]
        console.print(f"  Output tail: {tail!r}")
        return
    try:
        ReviewResult.model_validate(data)
    except PydanticValidationError as exc:
        console.print("  JSON parsed but does not match the ReviewResult schema:")
        for error in exc.errors()[:10]:
            location = ".".join(str(part) for part in error["loc"]) or "<root>"
            console.print(f"    - {location}: {error['msg']}")
        console.print("  Run `arena schema` to see the full expected JSON Schema.")


def verify_reviewer(
    benchmark_set: Path,
    command: str,
    case_id: str | None,
    timeout_seconds: int,
    reveal_metadata: bool,
    enable_repair: bool,
) -> None:
    console = Console()
    reviewer = CustomCommandReviewer(command, timeout_seconds, reveal_metadata, enable_repair)
    # Build the reviewer context from the immutable snapshot, not the mutable source.
    try:
        with snapshot_pack(benchmark_set) as snapshot:
            cases = snapshot.load()
            case = (
                next((item for item in cases if item.id == case_id), None)
                if case_id
                else (cases[0] if cases else None)
            )
            if case is None:
                Console(stderr=True).print(f"[red]ERROR[/red] case not found: {case_id}")
                raise typer.Exit(code=1)
            console.print(f"Running wrapper against case [bold]{case.id}[/bold] (blind payload)...")
            response = reviewer.review(build_context(case))
    except ArenaError as exc:
        Console(stderr=True).print(f"[red]ERROR[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"status={response.parse_status} attempts={response.parse_attempts} "
        f"actions={response.parse_actions} "
        f"findings(input={response.input_finding_count} retained={response.retained_finding_count} "
        f"dropped={response.dropped_finding_count}) latency={response.latency_ms}ms"
    )
    parsed = response.parsed_response
    if response.parse_status == "exact" and parsed is not None:
        console.print(
            f"[green]VALID[/green] {len(parsed.findings)} finding(s), "
            f"overall_risk={parsed.overall_risk}"
        )
        return
    if response.parse_status in {"tolerant", "repaired"} and parsed is not None:
        # Salvage succeeded but the output is NOT exact: never present it as contract
        # compliance, and make clear the run would be non-comparable.
        console.print(
            "[yellow]SALVAGED (DEVELOPMENT ONLY, NON-COMPARABLE)[/yellow] "
            f"{len(parsed.findings)} finding(s) after salvage "
            f"({response.parse_status}); a comparable run requires exact output."
        )
        if response.dropped_finding_count:
            console.print(
                f"  dropped {response.dropped_finding_count} invalid finding(s): "
                f"{response.parse_error_summary}"
            )
        return
    console.print("[red]INVALID[/red] the wrapper's output failed the reviewer contract:")
    _diagnose(response.raw_response, console)
    raise typer.Exit(code=1)
