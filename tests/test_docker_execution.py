"""Hardened Docker backend: locked-down args, no silent fallback, digest recorded."""

import os
import sys
from pathlib import Path

import pytest

from arena.execution.test_executor import TestExecutionRequest, TestExecutor


def test_docker_args_are_hardened():
    request = TestExecutionRequest(
        case_id="c",
        workspace_path=Path("/tmp"),
        test_command="python -c pass",
        timeout_seconds=30,
        docker_image="python:3.12-slim",
    )
    args = TestExecutor._docker_args(request, ["python", "-c", "pass"], container_name="arena-x")
    joined = " ".join(args)
    for flag in (
        "--rm",
        "--name arena-x",
        "--network none",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--pids-limit",
        "--memory",
        "--cpus",
        "--read-only",
        "--tmpfs",
    ):
        assert flag in joined, flag
    # The image and command are always last, in order.
    assert args[-4:] == ["python:3.12-slim", "python", "-c", "pass"]
    if sys.platform != "win32":
        assert "--user" in joined


def test_docker_required_case_never_falls_back_to_local(monkeypatch, tmp_path):
    # Even with local execution allowed, an image-declaring case must not run
    # locally when Docker is unavailable.
    monkeypatch.setattr(TestExecutor, "_docker_available", staticmethod(lambda: False))
    request = TestExecutionRequest(
        case_id="c",
        workspace_path=tmp_path,
        test_command="python -c pass",
        timeout_seconds=10,
        docker_image="python:3.12-slim",
        allow_local_execution=True,
    )
    result = TestExecutor().execute(request)
    assert result.execution_mode == "skipped"
    assert result.error == "docker_required_but_unavailable"


docker_tests = pytest.mark.skipif(
    not os.getenv("ARENA_DOCKER_TESTS"),
    reason="set ARENA_DOCKER_TESTS=1 to exercise a real Docker run",
)


@docker_tests
def test_real_docker_run_passes_and_records_digest(tmp_path):
    request = TestExecutionRequest(
        case_id="dockint",
        workspace_path=tmp_path,
        test_command='python -c "assert 1 + 1 == 2"',
        timeout_seconds=120,
        docker_image="python:3.12-slim",
    )
    result = TestExecutor().execute(request)
    assert result.execution_mode == "docker"
    assert result.passed is True
    assert result.image_digest is not None
    assert "sha256:" in result.image_digest
