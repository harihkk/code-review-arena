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
        "--pull never",
        "--name arena-x",
        "--network none",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "--pids-limit",
        "--memory",
        "--cpus",
        "--read-only",
        "--tmpfs",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
    ):
        assert flag in joined, flag
    # The image and command are always last, in order.
    assert args[-4:] == ["python:3.12-slim", "python", "-c", "pass"]
    if sys.platform != "win32":
        assert "--user" in joined


def test_docker_command_routes_pytest_through_python_m():
    # A pytest case is rewritten to `python -m pytest` so workspace imports work.
    request = TestExecutionRequest(
        case_id="c",
        workspace_path=Path("/tmp"),
        test_command="pytest -q tests",
        timeout_seconds=30,
        docker_image="arena-bench:1",
    )
    args = TestExecutor._docker_args(request, ["pytest", "-q", "tests"], container_name="arena-x")
    assert args[-6:] == ["arena-bench:1", "python", "-m", "pytest", "-q", "tests"]


def test_docker_args_mount_hidden_tests_read_only(tmp_path):
    (tmp_path / "tests").mkdir()
    request = TestExecutionRequest(
        case_id="c",
        workspace_path=tmp_path,
        test_command="pytest -q tests",
        timeout_seconds=30,
        docker_image="arena-bench:1",
        readonly_paths=["tests"],
    )
    args = TestExecutor._docker_args(request, ["pytest", "-q", "tests"], container_name="arena-x")
    assert f"{(tmp_path / 'tests').resolve()}:/workspace/tests:ro" in args


def test_missing_image_is_skipped_not_pulled(monkeypatch, tmp_path):
    # Docker is up but the (untrusted) image is absent: skip rather than let
    # `docker run` reach the network to pull and run unvetted code.
    monkeypatch.setattr(TestExecutor, "_docker_available", staticmethod(lambda: True))
    monkeypatch.setattr(TestExecutor, "_image_present", staticmethod(lambda image: False))
    request = TestExecutionRequest(
        case_id="c",
        workspace_path=tmp_path,
        test_command="pytest -q",
        timeout_seconds=10,
        docker_image="arena-bench:1",
    )
    result = TestExecutor().execute(request)
    assert result.execution_mode == "skipped"
    assert result.error == "docker_image_not_present"


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


@docker_tests
def test_real_docker_pytest_collects_a_workspace_module(tmp_path):
    # Regression: the bare `pytest` script does not put the workspace root on
    # sys.path, so a test importing a top-level module failed to collect in the
    # container. The command must be routed through `python -m pytest`.
    image = os.getenv("ARENA_BENCH_IMAGE", "arena-bench:1")
    (tmp_path / "calc.py").write_text("def is_adult(age):\n    return age >= 18\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from calc import is_adult\ndef test_adult():\n    assert is_adult(18) is True\n"
    )
    result = TestExecutor().execute(
        TestExecutionRequest(
            case_id="dockmod",
            workspace_path=tmp_path,
            test_command="pytest -q tests",
            timeout_seconds=120,
            docker_image=image,
        )
    )
    assert result.execution_mode == "docker"
    assert result.passed is True, result.stdout + result.stderr


@docker_tests
def test_real_docker_read_only_tests_cannot_be_rewritten(tmp_path):
    # A patch that rewrites the hidden tests to force a pass must fail: the tests
    # are mounted read-only, so the write raises and the host copy is untouched.
    image = os.getenv("ARENA_BENCH_IMAGE", "arena-bench:1")
    tests = tmp_path / "tests"
    tests.mkdir()
    victim = tests / "test_victim.py"
    victim.write_text("def test_v():\n    assert False\n")
    (tests / "test_attacker.py").write_text(
        "from pathlib import Path\n"
        "def test_rewrite():\n"
        "    Path(__file__).parent.joinpath('test_victim.py').write_text("
        "'def test_v():\\n    assert True\\n')\n"
    )
    original = victim.read_text()
    result = TestExecutor().execute(
        TestExecutionRequest(
            case_id="dockro",
            workspace_path=tmp_path,
            test_command="pytest -q tests",
            timeout_seconds=120,
            docker_image=image,
            readonly_paths=["tests"],
        )
    )
    assert result.execution_mode == "docker"
    assert result.passed is False  # the rewrite hit a read-only filesystem
    assert victim.read_text() == original  # the hidden test was never modified
