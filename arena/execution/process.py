"""Run a subprocess as its own process group and kill the whole tree on exit.

``subprocess.run(timeout=...)`` only signals the direct child, so descendants a
fixture spawns (background shells, dev servers, grandchildren) survive a timeout
and contaminate later cases, hold ports, or keep burning CPU. We start the child
in a new session and, on timeout, cancellation, or any error, signal the entire
process group.
"""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

# How long to wait for a group to exit after each signal before escalating.
_GROUP_GRACE_SECONDS = 2.0
# Read size per pipe wake-up. Output is capped incrementally, so the parent
# never buffers more than the limit plus at most one chunk.
_READ_CHUNK_BYTES = 65536


@dataclass
class SupervisedResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    # True when the child's combined output hit output_limit and was capped (the
    # process group is then terminated so a flood cannot exhaust parent memory).
    output_limit_exceeded: bool = False


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
    # Binary, unbuffered pipes: we count bytes, cap incrementally, and decode
    # ourselves with replacement, so a flood cannot exhaust parent memory and
    # raw bytes never raise UnicodeDecodeError.
    process = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        start_new_session=True,  # own session => own process group for tree-kill
        preexec_fn=preexec_fn,
    )
    try:
        try:
            stdout_b, stderr_b, exceeded, timed_out = _pump(process, timeout, output_limit)
        except BaseException:
            # Cancellation or any unexpected error: never leave the tree running.
            _terminate_group(process)
            raise
        if timed_out or exceeded:
            _terminate_group(process)
        else:
            try:
                process.wait(timeout=_GROUP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                _terminate_group(process)
        return SupervisedResult(
            process.returncode,
            stdout_b.decode("utf-8", errors="replace"),
            stderr_b.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            output_limit_exceeded=exceeded,
        )
    finally:
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass


def _pump(
    process: subprocess.Popen, timeout: float, output_limit: int | None
) -> tuple[bytearray, bytearray, bool, bool]:
    """Read stdout and stderr in bounded chunks until EOF, deadline, or cap.

    Returns (stdout_bytes, stderr_bytes, output_limit_exceeded, timed_out). The
    combined buffered bytes never exceed output_limit by more than one chunk, so
    a runaway producer cannot grow parent memory without bound; on overflow it
    returns early so the caller can kill the whole process group.
    """
    stdout, stderr = process.stdout, process.stderr
    assert stdout is not None and stderr is not None  # PIPE was requested for both
    selector = selectors.DefaultSelector()
    buffers: dict[object, bytearray] = {stdout: bytearray(), stderr: bytearray()}
    for stream in (stdout, stderr):
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)
    out, err = buffers[stdout], buffers[stderr]
    deadline = monotonic() + timeout
    open_streams: set[object] = {stdout, stderr}
    exceeded = False
    try:
        while open_streams:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return out, err, exceeded, True
            for key, _ in selector.select(timeout=min(remaining, 0.5)):
                try:
                    chunk = os.read(key.fd, _READ_CHUNK_BYTES)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    open_streams.discard(key.fileobj)
                    continue
                buffers[key.fileobj].extend(chunk)
            if output_limit is not None and len(out) + len(err) > output_limit:
                _trim_combined(out, err, output_limit)
                return out, err, True, False
        return out, err, exceeded, False
    finally:
        selector.close()


def _trim_combined(out: bytearray, err: bytearray, limit: int) -> None:
    """Drop bytes so len(out) + len(err) == limit, trimming stderr first."""
    overflow = len(out) + len(err) - limit
    if overflow <= 0:
        return
    trim_err = min(len(err), overflow)
    if trim_err:
        del err[len(err) - trim_err :]
    overflow -= trim_err
    if overflow > 0:
        del out[len(out) - overflow :]


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
