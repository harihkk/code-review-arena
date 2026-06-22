from pathlib import Path

from rich.console import Console
from rich.table import Table

from arena.benchmark.snapshot import snapshot_pack


def list_cases(benchmark_set: Path) -> None:
    table = Table()
    table.add_column("ID", overflow="fold", min_width=28)
    table.add_column("Category")
    table.add_column("Severity")
    table.add_column("Stack")
    # Read from the immutable snapshot, not the mutable source.
    with snapshot_pack(benchmark_set) as snapshot:
        for case in snapshot.load():
            table.add_row(case.id, case.category, case.severity, ", ".join(case.stack))
    Console(width=140).print(table)
