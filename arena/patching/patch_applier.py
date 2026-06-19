"""Apply suggested unified diffs only inside isolated run workspaces."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath

from arena.patching.patch_models import PatchApplyRequest, PatchApplyResult
from arena.patching.patch_parser import (
    referenced_paths,
    touched_files,
    unsafe_patch_modes,
    unsafe_patch_paths,
)
from arena.security.paths import assert_safe_delete_target, validate_case_id

# Files that influence test collection or execution regardless of location;
# a patch may never create or modify them.
PROTECTED_BASENAMES = frozenset(
    {"conftest.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"}
)


def is_protected_path(path: str, protected_paths: list[str]) -> bool:
    """True when a diff path is a protected file or sits under a protected prefix."""
    if PurePosixPath(path).name in PROTECTED_BASENAMES:
        return True
    for rule in protected_paths:
        normalized = rule.strip("/")
        if not normalized:
            continue
        if path == normalized or path.startswith(normalized + "/"):
            return True
    return False


class PatchApplier:
    def __init__(self, runs_root: Path, timeout_seconds: int = 15) -> None:
        self.runs_root = runs_root
        self.timeout_seconds = timeout_seconds

    def apply(self, request: PatchApplyRequest) -> PatchApplyResult:
        started = time.perf_counter()
        # case_id and run_id become physical path components; validate them as
        # slugs so an adversarial pack cannot escape the workspaces root.
        validate_case_id(request.case_id)
        validate_case_id(request.run_id)
        workspaces_root = self.runs_root / request.run_id / "workspaces"
        workspace = workspaces_root / request.case_id
        if workspace.exists():
            # Never rmtree outside the workspaces root (also rejects a symlinked
            # workspace pointing elsewhere).
            assert_safe_delete_target(workspaces_root, workspace)
            shutil.rmtree(workspace)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        # symlinks=True copies links as links rather than following them into host
        # data; admission already rejects symlinks, this is defense in depth.
        shutil.copytree(request.source_dir, workspace, symlinks=True)
        paths = touched_files(request.patch_text or "")
        if not request.patch_text.strip():
            return self._result(request, workspace, False, "no_patch_provided", paths, started)

        unsafe = unsafe_patch_paths(request.patch_text) + unsafe_patch_modes(request.patch_text)
        if unsafe:
            return self._result(
                request,
                workspace,
                False,
                f"patch_unsafe_paths: {', '.join(unsafe)}",
                paths,
                started,
                unsafe_paths=unsafe,
            )
        # Check protection against every path the diff names (sources, targets,
        # renames, copies), not just the +++ targets in touched_files: a pure
        # "rename to conftest.py" has no +++ line but must still be rejected.
        protected = [
            path
            for path in referenced_paths(request.patch_text)
            if is_protected_path(path, request.protected_paths)
        ]
        if protected:
            return self._result(
                request,
                workspace,
                False,
                f"patch_touched_protected_files: {', '.join(protected)}",
                paths,
                started,
                touched_protected=protected,
            )

        patch_file = workspace / ".arena-suggested.patch"
        patch_file.write_text(request.patch_text, encoding="utf-8")
        try:
            clean = self._git_apply(workspace, patch_file, reject=False)
            if clean.returncode == 0:
                return self._result(request, workspace, True, None, paths, started)
            rejected = self._git_apply(workspace, patch_file, reject=True)
            details = "\n".join(
                part.strip()
                for part in [clean.stderr, clean.stdout, rejected.stderr, rejected.stdout]
                if part.strip()
            )
            return self._result(
                request, workspace, False, details or "patch_did_not_apply_cleanly", paths, started
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return self._result(request, workspace, False, str(exc), paths, started)
        finally:
            patch_file.unlink(missing_ok=True)

    def _git_apply(
        self, workspace: Path, patch_file: Path, *, reject: bool
    ) -> subprocess.CompletedProcess[str]:
        args = ["git", "apply"]
        if reject:
            args.append("--reject")
        args.extend(["--whitespace=nowarn", str(patch_file.resolve())])
        return subprocess.run(
            args,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
        )

    @staticmethod
    def _result(
        request: PatchApplyRequest,
        workspace: Path,
        applied: bool,
        error: str | None,
        paths: list[str],
        started: float,
        *,
        touched_protected: list[str] | None = None,
        unsafe_paths: list[str] | None = None,
    ) -> PatchApplyResult:
        return PatchApplyResult(
            case_id=request.case_id,
            finding_id=request.finding_id,
            applied=applied,
            error=error,
            touched_files=paths,
            touched_protected=touched_protected or [],
            unsafe_paths=unsafe_paths or [],
            workspace_path=str(workspace),
            patch_text=request.patch_text,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
