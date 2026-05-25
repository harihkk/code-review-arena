"""Contracts for deterministic, tolerant structural validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field

from arena.core.models import BenchmarkCase, Finding


class ValidatorContext(BaseModel):
    case_id: str
    workspace_path: Path
    changed_files: list[str] = Field(default_factory=list)
    finding: Finding | None = None
    case_metadata: BenchmarkCase


class ValidatorResult(BaseModel):
    name: str
    passed: bool
    confidence: float = Field(ge=0, le=1)
    message: str
    evidence: list[str] = Field(default_factory=list)
    error: str | None = None


class BaseValidator(ABC):
    name: str

    @abstractmethod
    def validate(self, context: ValidatorContext) -> ValidatorResult:
        """Validate a patched workspace without executing untrusted code."""


def read_expected_file(context: ValidatorContext) -> tuple[str, str]:
    path = context.case_metadata.ground_truth.primary_bug.files[0].path
    full_path = context.workspace_path / path
    return path, full_path.read_text(encoding="utf-8")
