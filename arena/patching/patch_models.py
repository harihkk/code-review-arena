"""Typed records produced while applying and validating reviewer patches."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from arena.validators.base import ValidatorResult


class PatchApplyRequest(BaseModel):
    case_id: str
    source_dir: Path
    patch_text: str
    run_id: str
    finding_id: str | None = None
    protected_paths: list[str] = Field(default_factory=list)


class PatchApplyResult(BaseModel):
    case_id: str
    finding_id: str | None = None
    applied: bool
    error: str | None = None
    touched_files: list[str] = Field(default_factory=list)
    touched_protected: list[str] = Field(default_factory=list)
    unsafe_paths: list[str] = Field(default_factory=list)
    workspace_path: str
    patch_text: str
    duration_ms: int
    # Authoritative Git evidence (Phase 1D); optional/defaulted for compatibility.
    reason: str | None = None
    git_diagnostic: str | None = None
    patch_sha256: str | None = None
    git_version: str | None = None
    object_format: str | None = None
    baseline_tree: str | None = None
    result_tree: str | None = None
    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    mode_changes: list[str] = Field(default_factory=list)


class PatchValidationResult(BaseModel):
    patch_provided: bool
    patch_applied: bool
    tests_passed: bool | None = None
    structural_validation_passed: bool | None = None
    validators: list[ValidatorResult] = Field(default_factory=list)
    error: str | None = None
