"""The process supervisor kills the whole tree on timeout and caps output."""

import os
import sys
import time

import pytest

from arena.execution.process import run_supervised
from arena.execution.test_executor import TestExecutionRequest, TestExecutor

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group kill")


def _path_env() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "")}


@posix_only
def test_run_supervised_kills_descendants_on_timeout(tmp_path):
    marker = tmp_path / "survived.txt"
    # The child backgrounds a grandchild that writes a marker after 2s, then
    # sleeps far past the timeout. If the tree is killed, the marker never lands.
    script = (
        "import subprocess, time\n"
        f"subprocess.Popen(['sh', '-c', 'sleep 2; echo alive > {marker}'])\n"
        "time.sleep(30)\n"
    )
    result = run_supervised(
        [sys.executable, "-c", script], cwd=tmp_path, env=_path_env(), timeout=1
    )
    assert result.timed_out is True
    time.sleep(3)  # well past the grandchild's 2s write window
    assert not marker.exists()


def test_run_supervised_truncates_output(tmp_path):
    result = run_supervised(
        [sys.executable, "-c", "print('x' * 5000)"],
        cwd=tmp_path,
        env=_path_env(),
        timeout=10,
        output_limit=100,
    )
    assert result.timed_out is False
    assert "truncated" in result.stdout
    assert len(result.stdout) < 5000


@posix_only
def test_executor_reports_timeout(tmp_path):
    request = TestExecutionRequest(
        case_id="c",
        workspace_path=tmp_path,
        test_command=[sys.executable, "-c", "import time; time.sleep(30)"],
        timeout_seconds=1,
        allow_local_execution=True,
    )
    result = TestExecutor().execute(request)
    assert result.timed_out is True
    assert result.passed is False
    assert result.error == "test_execution_timed_out"
