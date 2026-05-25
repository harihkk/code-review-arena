from pathlib import Path

from rich.console import Console

from arena.reports.html_report import render_html
from arena.reports.json_report import read_json_report
from arena.reports.markdown_report import render_markdown


def report(run_path: Path, report_format: str) -> None:
    run = read_json_report(run_path)
    if report_format == "json":
        Console().print_json(run.model_dump_json())
    elif report_format == "html":
        Console().print(render_html(run))
    else:
        Console().print(render_markdown(run))
