"""Optional test tool wrapper."""

from pathlib import Path

from arena.execution.subprocess_runner import CommandResult, run_command


def run_tests(root: Path, command: str, timeout_seconds: int) -> CommandResult:
    return run_command(command, cwd=root, timeout_seconds=timeout_seconds)
