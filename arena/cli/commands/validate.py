from pathlib import Path

import typer
from rich.console import Console

from arena.benchmark.dataset_validator import validate_dataset
from arena.benchmark.snapshot import snapshot_pack
from arena.core.errors import ValidationError


def validate(benchmark_set: Path) -> None:
    # Validate the immutable snapshot, not the live source: snapshot creation also
    # rejects unsafe trees (symlinks, special files, collisions) as validation errors.
    try:
        with snapshot_pack(benchmark_set) as snapshot:
            errors = validate_dataset(snapshot.root)
    except ValidationError as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            Console(stderr=True).print(f"[red]ERROR[/red] {error}")
        raise typer.Exit(code=1)
    Console().print(f"[green]Valid[/green] benchmark set: {benchmark_set}")
