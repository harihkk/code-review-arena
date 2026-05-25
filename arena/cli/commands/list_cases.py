from pathlib import Path

from rich.console import Console
from rich.table import Table

from arena.benchmark.case_loader import load_cases


def list_cases(benchmark_set: Path) -> None:
    table = Table()
    table.add_column("ID", overflow="fold", min_width=28)
    table.add_column("Category")
    table.add_column("Severity")
    table.add_column("Stack")
    for case in load_cases(benchmark_set):
        table.add_row(case.id, case.category, case.severity, ", ".join(case.stack))
    Console(width=140).print(table)
