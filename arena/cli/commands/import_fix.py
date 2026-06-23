"""`arena import-fix`: deterministic local historical-fix ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from arena.core.errors import ImportFixError
from arena.importer.historical_fix import import_fix


def import_fix_command(
    *,
    repo: Path,
    buggy_commit: str,
    fixed_commit: str,
    spec: Path,
    output: Path,
    source_label: str | None,
    json_output: bool,
) -> None:
    try:
        result = import_fix(
            repo_path=repo,
            buggy_commit=buggy_commit,
            fixed_commit=fixed_commit,
            spec_path=spec,
            output=output,
            source_label=source_label,
        )
    except ImportFixError as exc:
        if json_output:
            typer.echo(json.dumps({"ok": False, "reason": exc.reason, "error": str(exc)}))
        else:
            typer.echo(f"import-fix failed [{exc.reason}]: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "ok": True,
                    "output_path": str(result.output_path),
                    "case_id": result.case_id,
                    "buggy_commit": result.buggy_commit,
                    "fixed_commit": result.fixed_commit,
                    "merge_base": result.merge_base,
                    "object_format": result.object_format,
                    "buggy_source_file_count": result.buggy_source_file_count,
                    "fixed_source_file_count": result.fixed_source_file_count,
                    "union_source_file_count": result.union_source_file_count,
                    "source_file_count": result.source_file_count,
                    "fixed_test_file_count": result.fixed_test_file_count,
                    "repair_changed_paths": result.repair_changed_paths,
                    "test_changed_paths": result.test_changed_paths,
                    "pack_checksum": result.pack_checksum,
                    "validation": "passed" if result.validation_ok else "failed",
                    "contamination": "clean" if result.contamination_ok else "found",
                    "certification": result.certification,
                },
                indent=2,
            )
        )
        return

    typer.echo(f"Imported reverse-fix candidate pack: {result.output_path}")
    typer.echo(f"  case id:            {result.case_id}")
    typer.echo(f"  buggy commit:       {result.buggy_commit}")
    typer.echo(f"  fixed commit:       {result.fixed_commit}")
    typer.echo(f"  object format:      {result.object_format}")
    typer.echo(
        f"  source files:       buggy={result.buggy_source_file_count} "
        f"fixed={result.fixed_source_file_count} union={result.union_source_file_count}"
    )
    typer.echo(f"  test files:         {result.fixed_test_file_count}")
    typer.echo(f"  repair changed:     {', '.join(result.repair_changed_paths) or '(none)'}")
    typer.echo(f"  test changed:       {', '.join(result.test_changed_paths) or '(none)'}")
    typer.echo(f"  pack checksum:      {result.pack_checksum}")
    typer.echo(f"  validation:         {'passed' if result.validation_ok else 'failed'}")
    typer.echo(f"  contamination:      {'clean' if result.contamination_ok else 'found'}")
    typer.echo(f"  certification:      {result.certification}")
    typer.echo("\nThis is a synthetic reverse-review case derived from a real historical fix,")
    typer.echo("not the original bug-introducing pull request. Next, review it manually and run:")
    typer.echo(f"  arena validate {result.output_path}")
    typer.echo(f"  arena lint-cases {result.output_path} --strict")
    typer.echo(f"  arena certify-pack {result.output_path}")
