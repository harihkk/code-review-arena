from pathlib import Path

import typer
from rich.console import Console

from arena.benchmark.dataset_validator import validate_dataset


def validate(benchmark_set: Path) -> None:
    errors = validate_dataset(benchmark_set)
    if errors:
        for error in errors:
            Console(stderr=True).print(f"[red]ERROR[/red] {error}")
        raise typer.Exit(code=1)
    Console().print(f"[green]Valid[/green] benchmark set: {benchmark_set}")
