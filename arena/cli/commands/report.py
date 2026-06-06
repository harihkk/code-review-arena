from pathlib import Path

import typer
from rich.console import Console

from arena.reports.html_report import render_html
from arena.reports.json_report import read_json_report
from arena.reports.markdown_report import render_markdown

_FORMATS = {"markdown", "json", "html"}


def report(run_path: Path, report_format: str) -> None:
    if report_format not in _FORMATS:
        Console(stderr=True).print(
            f"[red]ERROR[/red] unknown --format '{report_format}'. "
            f"Choose one of: {', '.join(sorted(_FORMATS))}"
        )
        raise typer.Exit(code=1)
    if not run_path.is_file():
        Console(stderr=True).print(f"[red]ERROR[/red] run report not found: {run_path}")
        raise typer.Exit(code=1)
    try:
        run = read_json_report(run_path)
    except Exception as exc:  # noqa: BLE001 - surface a readable error, not a traceback.
        Console(stderr=True).print(f"[red]ERROR[/red] could not read run report {run_path}: {exc}")
        raise typer.Exit(code=1) from exc

    if report_format == "json":
        Console().print_json(run.model_dump_json())
    elif report_format == "html":
        Console().print(render_html(run))
    else:
        Console().print(render_markdown(run))
