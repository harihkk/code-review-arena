"""Controlled local command execution for benchmark fixtures."""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path

from pydantic import BaseModel

from arena.execution.hardening import resource_limiter, sandboxed_home_env


class CommandResult(BaseModel):
    command: str
    return_code: int
    output: str
    duration_ms: int
    timed_out: bool = False


def run_command(command: str, cwd: Path, timeout_seconds: int) -> CommandResult:
    started = time.perf_counter()
    arguments = shlex.split(command)
    if arguments and arguments[0] == "pytest":
        arguments = [sys.executable, "-m", "pytest", *arguments[1:]]
    try:
        with sandboxed_home_env() as env:
            completed = subprocess.run(
                arguments,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=env,
                preexec_fn=resource_limiter(timeout_seconds),
            )
        output = (completed.stdout + "\n" + completed.stderr).strip()
        return CommandResult(
            command=command,
            return_code=completed.returncode,
            output=output,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            return_code=124,
            output=f"Timed out after {timeout_seconds}s: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
            timed_out=True,
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=command,
            return_code=127,
            output=f"Command unavailable: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
