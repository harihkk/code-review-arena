"""Adversarial tests for bounded subprocess output in arena/execution/process.py.

The old path read all output via communicate() and truncated the string by
character count afterward, so a flood could exhaust parent memory, binary bytes
could raise UnicodeDecodeError, and the cap was characters not bytes.
"""

import os
import sys

import pytest

from arena.execution.process import run_supervised

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="bounded reader is POSIX-only")

ENV = {"PATH": os.environ.get("PATH", "")}


def _run(script: str, *, timeout: float = 15.0, output_limit: int | None, tmp_path):
    return run_supervised(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=ENV,
        timeout=timeout,
        output_limit=output_limit,
    )


def test_output_flood_does_not_grow_memory_unbounded(tmp_path):
    # Writes forever; the parent must cap it and kill the tree, not buffer it all.
    flood = "import sys\nwhile True:\n    sys.stdout.write('A' * 65536)\n    sys.stdout.flush()\n"
    result = _run(flood, output_limit=10_000, tmp_path=tmp_path)
    assert result.output_limit_exceeded is True
    # Captured output is bounded near the limit (at most one extra read chunk).
    assert len(result.stdout.encode("utf-8")) <= 10_000 + 65536


def test_output_limit_terminates_the_process(tmp_path):
    # Floods past the limit, then would sleep for a minute; if the overflow kills
    # the process, the call returns long before the sleep elapses.
    script = (
        "import sys, time\nsys.stdout.write('A' * 200000)\nsys.stdout.flush()\ntime.sleep(60)\n"
    )
    result = _run(script, timeout=30.0, output_limit=5_000, tmp_path=tmp_path)
    assert result.output_limit_exceeded is True
    assert result.returncode is not None  # the process was reaped, not left running


def test_combined_stdout_stderr_limit_is_enforced(tmp_path):
    script = (
        "import sys\n"
        "sys.stdout.write('O' * 1000)\nsys.stdout.flush()\n"
        "sys.stderr.write('E' * 1000)\nsys.stderr.flush()\n"
    )
    result = _run(script, output_limit=1_500, tmp_path=tmp_path)
    assert result.output_limit_exceeded is True
    assert len(result.stdout) + len(result.stderr) <= 1_500


def test_binary_output_does_not_raise_unicode_decode_error(tmp_path):
    script = "import os\nos.write(1, b'\\xff\\xfe\\x00\\x80' * 100)\n"
    result = _run(script, output_limit=10_000, tmp_path=tmp_path)
    assert isinstance(result.stdout, str)  # decoded with replacement, no exception


def test_output_limit_is_measured_in_bytes(tmp_path):
    # 200 euro signs = 200 characters but 600 UTF-8 bytes. With a 400-byte limit,
    # a byte-measured cap trips; a character-measured one (200 < 400) would not.
    script = "import sys\nsys.stdout.write('\\u20ac' * 200)\nsys.stdout.flush()\n"
    result = _run(script, output_limit=400, tmp_path=tmp_path)
    assert result.output_limit_exceeded is True
