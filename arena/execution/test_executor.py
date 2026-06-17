"""Safely execute post-patch tests inside an isolated workspace."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from arena.core.errors import ValidationError
from arena.execution.commands import parse_test_commands, pin_interpreter
from arena.execution.hardening import resource_limiter, sandbox_env
from arena.execution.process import run_supervised

# Cap captured stdout/stderr so a noisy or malicious fixture cannot exhaust memory.
OUTPUT_LIMIT_BYTES = 512_000


class TestExecutionRequest(BaseModel):
    __test__: ClassVar[bool] = False

    case_id: str
    workspace_path: Path
    test_command: str | list[str] | list[list[str]]
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
        try:
            commands = parse_test_commands(request.test_command)
        except ValidationError as exc:
            return self._skipped(request.case_id, f"invalid_test_command: {exc}")
        if not commands:
            return self._skipped(request.case_id, "empty_test_command")
        use_docker = bool(request.docker_image) and self._docker_available()
        if request.docker_image and not use_docker and not request.allow_local_execution:
            return self._skipped(request.case_id, "docker_unavailable_and_local_execution_disabled")
        if not use_docker and not request.allow_local_execution:
            return self._skipped(request.case_id, "local_execution_disabled")

        mode: Literal["docker", "local"] = "docker" if use_docker else "local"
        results: list[TestExecutionResult] = []
        for argv in commands:
            args = self._docker_args(request, argv) if use_docker else pin_interpreter(argv)
            result = self._run(request, args, mode)
            results.append(result)
            if not result.passed:
                break
        return self._combined(request.case_id, results, mode)

    @staticmethod
    def _combined(
        case_id: str, results: list[TestExecutionResult], mode: Literal["docker", "local"]
    ) -> TestExecutionResult:
        last = results[-1]
        if len(results) == 1:
            return last
        return TestExecutionResult(
            case_id=case_id,
            ran=True,
            passed=all(result.passed for result in results),
            exit_code=last.exit_code,
            stdout="\n".join(filter(None, (result.stdout for result in results))),
            stderr="\n".join(filter(None, (result.stderr for result in results))),
            duration_ms=sum(result.duration_ms for result in results),
            timed_out=any(result.timed_out for result in results),
            execution_mode=mode,
            error=last.error,
        )

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
        # run_supervised starts the child in its own session and kills the whole
        # process tree on timeout, so descendants cannot outlive the case.
        result = run_supervised(
            args,
            cwd=request.workspace_path,
            env=env,
            timeout=request.timeout_seconds,
            preexec_fn=preexec,
            output_limit=OUTPUT_LIMIT_BYTES,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        if result.timed_out:
            return TestExecutionResult(
                case_id=request.case_id,
                ran=True,
                passed=False,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
                timed_out=True,
                execution_mode=mode,
                error="test_execution_timed_out",
            )
        return TestExecutionResult(
            case_id=request.case_id,
            ran=True,
            passed=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=duration_ms,
            execution_mode=mode,
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
