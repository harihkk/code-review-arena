"""Load benchmark manifests and complete case contexts from disk."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from arena.benchmark.diff_loader import load_diff
from arena.core.errors import ValidationError
from arena.core.models import BenchmarkCase, CaseContext, CaseManifest, ReviewerCaseMetadata
from arena.patching.patch_parser import touched_files


@dataclass(frozen=True)
class ContextLimits:
    """Bounds on reviewer-visible file content injected per case."""

    max_files: int = 40
    max_total_bytes: int = 262_144
    max_file_bytes: int = 65_536

    @classmethod
    def from_env(cls) -> ContextLimits:
        return cls(
            max_files=int(os.getenv("ARENA_MAX_CONTEXT_FILES", str(cls.max_files))),
            max_total_bytes=int(os.getenv("ARENA_MAX_CONTEXT_BYTES", str(cls.max_total_bytes))),
            max_file_bytes=int(os.getenv("ARENA_MAX_CONTEXT_FILE_BYTES", str(cls.max_file_bytes))),
        )


def load_manifest(benchmark_dir: Path) -> CaseManifest:
    manifest_path = benchmark_dir / "manifest.yaml"
    if not manifest_path.exists():
        raise ValidationError(f"Missing manifest: {manifest_path}")
    try:
        manifest_data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        return CaseManifest.model_validate(manifest_data)
    except Exception as exc:
        raise ValidationError(f"Invalid manifest {manifest_path}: {exc}") from exc


def load_case(case_dir: Path) -> BenchmarkCase:
    config_path = case_dir / "case.yaml"
    if not config_path.is_file():
        raise ValidationError(f"Missing case.yaml: {config_path}")
    try:
        case = BenchmarkCase.model_validate(yaml.safe_load(config_path.read_text(encoding="utf-8")))
    except Exception as exc:
        raise ValidationError(f"Invalid case metadata in {config_path}: {exc}") from exc
    case.case_dir = case_dir
    return case


def load_cases(benchmark_dir: Path) -> list[BenchmarkCase]:
    manifest = load_manifest(benchmark_dir)
    return [load_case(benchmark_dir / case_id) for case_id in manifest.cases]


def _read_relevant_files(
    case: BenchmarkCase, diff_text: str, limits: ContextLimits
) -> tuple[dict[str, str], bool, list[str]]:
    """Read after-dir files bounded by limits, diff-referenced files first."""
    assert case.case_dir is not None
    after_dir = case.case_dir / case.input.after_dir
    all_paths = sorted(
        path.relative_to(after_dir).as_posix() for path in after_dir.rglob("*") if path.is_file()
    )
    available = set(all_paths)
    diff_first = [path for path in touched_files(diff_text) if path in available]
    ordered = diff_first + [path for path in all_paths if path not in set(diff_first)]

    contents: dict[str, str] = {}
    omitted: list[str] = []
    truncated = False
    total_bytes = 0
    for relative in ordered:
        if len(contents) >= limits.max_files or total_bytes >= limits.max_total_bytes:
            omitted.append(relative)
            continue
        text = (after_dir / relative).read_text(encoding="utf-8", errors="replace")
        raw = text.encode("utf-8")
        if len(raw) > limits.max_file_bytes:
            text = (
                raw[: limits.max_file_bytes].decode("utf-8", errors="replace")
                + "\n…[truncated by arena: file exceeds max_file_bytes]"
            )
            truncated = True
        size = len(text.encode("utf-8"))
        if total_bytes + size > limits.max_total_bytes:
            omitted.append(relative)
            total_bytes = limits.max_total_bytes  # budget exhausted; omit the rest too
            continue
        contents[relative] = text
        total_bytes += size
    return contents, truncated or bool(omitted), omitted


def build_context(
    case: BenchmarkCase,
    test_output: str = "",
    static_analysis_output: str = "",
    limits: ContextLimits | None = None,
) -> CaseContext:
    assert case.case_dir is not None
    diff_text = load_diff(case.case_dir / case.input.diff)
    relevant_files, truncated, omitted = _read_relevant_files(
        case, diff_text, limits or ContextLimits.from_env()
    )
    return CaseContext(
        case=ReviewerCaseMetadata(
            id=case.id,
            title=case.title,
            category=case.category,
            severity=case.severity,
            stack=case.stack,
            description=case.description,
        ),
        diff=diff_text,
        relevant_files=relevant_files,
        context_truncated=truncated,
        omitted_files=omitted,
        test_output=test_output,
        static_analysis_output=static_analysis_output,
        case_dir=case.case_dir,
    )
