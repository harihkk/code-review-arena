"""Strict, bounded, deterministic provenance for an imported case."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, StringConstraints

from arena.core import limits
from arena.core.errors import ImportFixError
from arena.core.models import _StrictExternal
from arena.security.paths import SafeRelativePath

PROVENANCE_SCHEMA_VERSION: Literal["2"] = "2"
DIFF_POLICY_VERSION = "1"

_LABEL_COMPONENT = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _check_source_label(value: str) -> str:
    """A stable ``owner/repository``-style label: no path/scheme/whitespace/control."""
    if not value or len(value) > limits.IMPORT_SOURCE_LABEL_LEN:
        raise ValueError("source label has an invalid length")
    if any(ord(ch) < 0x20 or ch.isspace() for ch in value):
        raise ValueError("source label contains whitespace or control characters")
    if ":" in value or "\\" in value or value.startswith("/"):
        raise ValueError("source label must not contain a scheme, drive, or absolute path")
    components = value.split("/")
    if not 1 <= len(components) <= 3:
        raise ValueError("source label must have 1 to 3 portable components")
    for component in components:
        if component in {".", ".."} or not _LABEL_COMPONENT.match(component):
            raise ValueError(f"source label component is not portable: {component!r}")
    return value


def validate_source_label(value: str) -> None:
    """Eagerly validate a source label, raising a stable ImportFixError on failure."""
    try:
        _check_source_label(value)
    except ValueError as exc:
        raise ImportFixError("invalid_source_label", str(exc)) from exc


SourceLabel = Annotated[str, AfterValidator(_check_source_label)]
_Hex = Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]


class Provenance(_StrictExternal):
    """Deterministic provenance: no time, host, user, or absolute/local paths."""

    provenance_schema_version: Literal["2"]
    mode: Literal["reverse_fix"]
    source_label: SourceLabel | None
    object_format: Literal["sha1", "sha256"]
    diff_policy_version: str
    buggy_commit: _Hex
    fixed_commit: _Hex
    merge_base: _Hex
    source_paths: list[SafeRelativePath]
    tests_root: SafeRelativePath | None
    buggy_source_files: list[SafeRelativePath]
    fixed_source_files: list[SafeRelativePath]
    fixed_test_files: list[SafeRelativePath]
    changed_source_paths: list[SafeRelativePath]
    changed_test_paths: list[SafeRelativePath]
    pr_diff_sha256: str
    reference_patch_sha256: str
