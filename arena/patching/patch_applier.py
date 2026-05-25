"""Apply suggested unified diffs only inside isolated run workspaces."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from arena.patching.patch_models import PatchApplyRequest, PatchApplyResult
from arena.patching.patch_parser import touched_files


class PatchApplier:
    def __init__(self, runs_root: Path, timeout_seconds: int = 15) -> None:
        self.runs_root = runs_root
        self.timeout_seconds = timeout_seconds

    def apply(self, request: PatchApplyRequest) -> PatchApplyResult:
        started = time.perf_counter()
        workspace = self.runs_root / request.run_id / "workspaces" / request.case_id
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(request.source_dir, workspace)
        paths = touched_files(request.patch_text or "")
        if not request.patch_text.strip():
            return self._result(request, workspace, False, "no_patch_provided", paths, started)

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
    ) -> PatchApplyResult:
        return PatchApplyResult(
            case_id=request.case_id,
            finding_id=request.finding_id,
            applied=applied,
            error=error,
            touched_files=paths,
            workspace_path=str(workspace),
            patch_text=request.patch_text,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
