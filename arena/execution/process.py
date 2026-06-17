"""Run a subprocess as its own process group and kill the whole tree on exit.

``subprocess.run(timeout=...)`` only signals the direct child, so descendants a
fixture spawns (background shells, dev servers, grandchildren) survive a timeout
and contaminate later cases, hold ports, or keep burning CPU. We start the child
in a new session and, on timeout, cancellation, or any error, signal the entire
process group.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# How long to wait for a group to exit after each signal before escalating.
_GROUP_GRACE_SECONDS = 2.0


@dataclass
class SupervisedResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


def _truncate(text: str, limit: int | None) -> str:
    if limit is None or len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {limit} bytes]"


def run_supervised(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    preexec_fn: Callable[[], None] | None = None,
    output_limit: int | None = None,
) -> SupervisedResult:
    """Run argv with a hard timeout, killing the whole process tree on timeout.

    On POSIX the child runs in a new session so the entire tree can be signalled;
    on Windows we fall back to ``subprocess.run`` (best-effort, no tree kill).
    """
    if sys.platform == "win32":
        return _run_windows(args, cwd=cwd, env=env, timeout=timeout, output_limit=output_limit)
    return _run_posix(
        args, cwd=cwd, env=env, timeout=timeout, preexec_fn=preexec_fn, output_limit=output_limit
    )


def _run_posix(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    preexec_fn: Callable[[], None] | None,
    output_limit: int | None,
) -> SupervisedResult:
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,  # own session => own process group for tree-kill
        preexec_fn=preexec_fn,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return SupervisedResult(
            process.returncode,
            _truncate(stdout, output_limit),
            _truncate(stderr, output_limit),
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        _terminate_group(process)
        stdout, stderr = _drain(process)
        return SupervisedResult(
            process.returncode,
            _truncate(stdout, output_limit),
            _truncate(stderr, output_limit),
            timed_out=True,
        )
    except BaseException:
        # Cancellation (KeyboardInterrupt) or any unexpected error: never leave
        # the tree running.
        _terminate_group(process)
        raise


def _terminate_group(process: subprocess.Popen) -> None:
    try:
        pgid = os.getpgid(process.pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=_GROUP_GRACE_SECONDS)
            return
        except subprocess.TimeoutExpired:
            continue


def _drain(process: subprocess.Popen) -> tuple[str, str]:
    try:
        return process.communicate(timeout=_GROUP_GRACE_SECONDS)
    except (subprocess.TimeoutExpired, ValueError):
        return "", ""


def _run_windows(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    output_limit: int | None,
) -> SupervisedResult:
    try:
        completed = subprocess.run(
            args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
        )
        return SupervisedResult(
            completed.returncode,
            _truncate(completed.stdout, output_limit),
            _truncate(completed.stderr, output_limit),
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return SupervisedResult(
            None, _truncate(stdout, output_limit), _truncate(stderr, output_limit), timed_out=True
        )
