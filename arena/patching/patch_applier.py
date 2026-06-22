"""Apply suggested unified diffs through the shared Git-authoritative pipeline.

``PatchApplier`` is a thin, compatibility-facing wrapper: it picks the run-scoped
workspace location and delegates the actual transaction to ``git_pipeline`` so the
post-application Git tree (not the patch text) is authoritative. Every patch class
goes through that one pipeline.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from arena.patching.git_pipeline import PROTECTED_BASENAMES, apply_patch
from arena.patching.patch_models import PatchApplyRequest, PatchApplyResult
from arena.security.paths import validate_case_id

__all__ = ["PROTECTED_BASENAMES", "PatchApplier", "is_protected_path"]


def is_protected_path(path: str, protected_paths: list[str]) -> bool:
    """True when a path is a protected file or sits under a protected prefix.

    Retained for early, non-authoritative diagnostics; the Git pipeline performs the
    final, authoritative protected-path enforcement on the actual changed paths.
    """
    if PurePosixPath(path).name in PROTECTED_BASENAMES:
        return True
    for rule in protected_paths:
        normalized = rule.strip("/")
        if normalized and (path == normalized or path.startswith(normalized + "/")):
            return True
    return False


class PatchApplier:
    def __init__(self, runs_root: Path, timeout_seconds: int = 15) -> None:
        self.runs_root = runs_root
        self.timeout_seconds = timeout_seconds

    def apply(self, request: PatchApplyRequest) -> PatchApplyResult:
        # case_id and run_id become physical path components; validate them as slugs
        # so an adversarial pack cannot escape the workspaces root.
        validate_case_id(request.case_id)
        validate_case_id(request.run_id)
        workspace = self.runs_root / request.run_id / "workspaces" / request.case_id
        result = apply_patch(
            source_dir=Path(request.source_dir),
            patch_text=request.patch_text or "",
            protected_paths=list(request.protected_paths),
            destination=workspace,
        )
        return PatchApplyResult(
            case_id=request.case_id,
            finding_id=request.finding_id,
            applied=result.applied,
            error=result.reason if not result.applied else None,
            reason=result.reason,
            touched_files=list(result.touched_files),
            touched_protected=list(result.protected_violations),
            unsafe_paths=list(result.unsafe_paths),
            workspace_path=str(workspace),
            patch_text=request.patch_text,
            duration_ms=result.duration_ms,
            patch_sha256=result.patch_sha256,
            git_version=result.git_version,
            object_format=result.object_format,
            baseline_tree=result.baseline_tree,
            result_tree=result.result_tree,
            added=list(result.added),
            modified=list(result.modified),
            deleted=list(result.deleted),
            mode_changes=list(result.mode_changes),
        )
