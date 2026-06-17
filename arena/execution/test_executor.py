"""Safely execute post-patch tests inside an isolated workspace."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from arena.core.errors import ValidationError
from arena.execution.commands import parse_test_commands, pin_interpreter
from arena.execution.hardening import resource_limiter, sandboxed_home_env
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
    # Resolved image digest (docker mode only) for reproducibility.
    image_digest: str | None = None


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
        # Docker is the standard backend. There is no silent Docker->local
        # fallback: a case that declares an image must run in Docker or be
        # skipped. Trusted-local is only for image-less cases that explicitly
        # opt in via allow_local_execution.
        if request.docker_image:
            if not self._docker_available():
                return self._skipped(request.case_id, "docker_required_but_unavailable")
            mode: Literal["docker", "local"] = "docker"
        elif request.allow_local_execution:
            mode = "local"
        else:
            return self._skipped(request.case_id, "local_execution_disabled")

        results: list[TestExecutionResult] = []
        for argv in commands:
            if mode == "docker":
                container = self._container_name(request.case_id)
                args = self._docker_args(request, argv, container_name=container)
            else:
                container = None
                args = pin_interpreter(argv)
            result = self._run(request, args, mode, container_name=container)
            results.append(result)
            if not result.passed:
                break
        combined = self._combined(request.case_id, results, mode)
        if mode == "docker":
            return combined.model_copy(
                update={"image_digest": self._image_digest(request.docker_image)}
            )
        return combined

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
    def _container_name(case_id: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_.-]", "-", case_id)[:40]
        return f"arena-{slug}-{uuid4().hex[:8]}"

    @staticmethod
    def _docker_args(
        request: TestExecutionRequest, args: list[str], *, container_name: str
    ) -> list[str]:
        assert request.docker_image is not None
        memory = os.getenv("ARENA_DOCKER_MEMORY", "2g")
        cpus = os.getenv("ARENA_DOCKER_CPUS", "2")
        pids = os.getenv("ARENA_DOCKER_PIDS", "256")
        tmpfs_size = os.getenv("ARENA_DOCKER_TMPFS_SIZE", "256m")
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            pids,
            "--memory",
            memory,
            "--cpus",
            cpus,
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={tmpfs_size}",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "-e",
            "HOME=/tmp",
            "-v",
            f"{request.workspace_path.resolve()}:/workspace",
            "-w",
            "/workspace",
        ]
        if sys.platform != "win32":
            # Run as the host user so the bind-mounted workspace stays writable
            # while the container process is non-root.
            command += ["--user", f"{os.getuid()}:{os.getgid()}"]
        command += [request.docker_image, *args]
        return command

    @staticmethod
    def _image_digest(image: str | None) -> str | None:
        if not image:
            return None
        result = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{index .RepoDigests 0}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        digest = result.stdout.strip()
        return digest or None

    @staticmethod
    def _force_remove_container(name: str) -> None:
        # docker run leaves the container running when its CLI is killed, so on
        # timeout we remove it by name; best-effort.
        subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

    def _run(
        self,
        request: TestExecutionRequest,
        args: list[str],
        mode: Literal["docker", "local"],
        *,
        container_name: str | None = None,
    ) -> TestExecutionResult:
        started = time.perf_counter()
        # run_supervised starts the child in its own session and kills the whole
        # process tree on timeout, so descendants cannot outlive the case.
        if mode == "local":
            # Untrusted fixtures: allowlisted env, isolated HOME/TMPDIR, bounded
            # resources, and no autoloaded pytest plugins (a candidate cannot
            # inject one via the workspace).
            with sandboxed_home_env(extra={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}) as env:
                result = run_supervised(
                    args,
                    cwd=request.workspace_path,
                    env=env,
                    timeout=request.timeout_seconds,
                    preexec_fn=resource_limiter(request.timeout_seconds),
                    output_limit=OUTPUT_LIMIT_BYTES,
                )
        else:
            # The docker CLI needs the caller's docker config; isolation comes
            # from the container itself.
            result = run_supervised(
                args,
                cwd=request.workspace_path,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                timeout=request.timeout_seconds,
                preexec_fn=None,
                output_limit=OUTPUT_LIMIT_BYTES,
            )
            if result.timed_out and container_name:
                self._force_remove_container(container_name)
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
