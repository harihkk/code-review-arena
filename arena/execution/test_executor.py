"""Safely execute post-patch tests inside an isolated workspace."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from arena.execution.hardening import resource_limiter, sandbox_env


class TestExecutionRequest(BaseModel):
    __test__: ClassVar[bool] = False

    case_id: str
    workspace_path: Path
    test_command: str | list[str]
    timeout_seconds: int = Field(ge=1)
    docker_image: str | None = None
    allow_local_execution: bool = False


class TestExecutionResult(BaseModel):
    __test__: ClassVar[bool] = False

    case_id: str
    ran: bool
    passed: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    timed_out: bool = False
    execution_mode: Literal["docker", "local", "skipped"]
    error: str | None = None


class TestExecutor:
    def execute(self, request: TestExecutionRequest) -> TestExecutionResult:
        if not request.workspace_path.is_dir():
            return self._skipped(request.case_id, "workspace_not_found")
        args = self._command_args(request.test_command)
        if not args:
            return self._skipped(request.case_id, "empty_test_command")
        if request.docker_image and self._docker_available():
            return self._run(request, self._docker_args(request, args), "docker")
        if request.docker_image and not request.allow_local_execution:
            return self._skipped(request.case_id, "docker_unavailable_and_local_execution_disabled")
        if not request.allow_local_execution:
            return self._skipped(request.case_id, "local_execution_disabled")
        if args[0] == "pytest":
            args = [sys.executable, "-m", "pytest", *args[1:]]
        return self._run(request, args, "local")

    @staticmethod
    def _command_args(command: str | list[str]) -> list[str]:
        return shlex.split(command) if isinstance(command, str) else list(command)

    @staticmethod
    def _docker_available() -> bool:
        if shutil.which("docker") is None:
            return False
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    @staticmethod
    def _docker_args(request: TestExecutionRequest, args: list[str]) -> list[str]:
        assert request.docker_image is not None
        return [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{request.workspace_path.resolve()}:/workspace",
            "-w",
            "/workspace",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            request.docker_image,
            *args,
        ]

    def _run(
        self,
        request: TestExecutionRequest,
        args: list[str],
        mode: Literal["docker", "local"],
    ) -> TestExecutionResult:
        started = time.perf_counter()
        if mode == "local":
            # Fixture commands are untrusted: allowlisted env, bounded resources.
            env = sandbox_env()
            preexec = resource_limiter(request.timeout_seconds)
        else:
            # The docker CLI needs the caller's docker config; isolation comes
            # from the container itself.
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            preexec = None
        try:
            completed = subprocess.run(
                args,
                cwd=request.workspace_path,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                check=False,
                env=env,
                preexec_fn=preexec,
            )
            return TestExecutionResult(
                case_id=request.case_id,
                ran=True,
                passed=completed.returncode == 0,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration_ms=int((time.perf_counter() - started) * 1000),
                execution_mode=mode,
            )
        except subprocess.TimeoutExpired as exc:
            return TestExecutionResult(
                case_id=request.case_id,
                ran=True,
                passed=False,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                duration_ms=int((time.perf_counter() - started) * 1000),
                timed_out=True,
                execution_mode=mode,
                error="test_execution_timed_out",
            )

    @staticmethod
    def _skipped(case_id: str, error: str) -> TestExecutionResult:
        return TestExecutionResult(
            case_id=case_id,
            ran=False,
            passed=False,
            execution_mode="skipped",
            error=error,
        )
