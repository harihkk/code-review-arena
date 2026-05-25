"""Optional static-analysis command wrapper."""

from pathlib import Path

from arena.execution.subprocess_runner import run_command


def run_static_analysis(root: Path, command: str, timeout_seconds: int) -> str:
    result = run_command(command, cwd=root, timeout_seconds=timeout_seconds)
    return result.output
