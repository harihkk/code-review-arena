"""Load benchmark manifests and complete case contexts from disk."""

from __future__ import annotations

from pathlib import Path

import yaml

from arena.benchmark.diff_loader import load_diff
from arena.core.errors import ValidationError
from arena.core.models import BenchmarkCase, CaseContext, CaseManifest, ReviewerCaseMetadata


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


def _read_relevant_files(case: BenchmarkCase) -> dict[str, str]:
    assert case.case_dir is not None
    after_dir = case.case_dir / case.input.after_dir
    contents: dict[str, str] = {}
    for path in after_dir.rglob("*"):
        if path.is_file():
            contents[path.relative_to(after_dir).as_posix()] = path.read_text(
                encoding="utf-8", errors="replace"
            )
    return contents


def build_context(
    case: BenchmarkCase, test_output: str = "", static_analysis_output: str = ""
) -> CaseContext:
    assert case.case_dir is not None
    return CaseContext(
        case=ReviewerCaseMetadata(
            id=case.id,
            title=case.title,
            category=case.category,
            severity=case.severity,
            stack=case.stack,
            description=case.description,
        ),
        diff=load_diff(case.case_dir / case.input.diff),
        relevant_files=_read_relevant_files(case),
        test_output=test_output,
        static_analysis_output=static_analysis_output,
        case_dir=case.case_dir,
    )
