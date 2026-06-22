"""Contracts for deterministic, tolerant structural validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel, Field

from arena.core.bounded_io import read_text_bounded
from arena.core.limits import PACK_FILE_BYTES
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
    return path, read_text_bounded(full_path, PACK_FILE_BYTES, label="workspace file")


def read_expected_source(context: ValidatorContext) -> tuple[str, str]:
    """The bug file with comments stripped: validators must match code, not prose."""
    from arena.validators.source_text import stripped_source

    path, text = read_expected_file(context)
    return path, stripped_source(path, text)
