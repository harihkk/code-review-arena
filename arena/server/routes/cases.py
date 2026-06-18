from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException

from arena.benchmark.case_loader import build_context, load_cases

router = APIRouter(prefix="/cases", tags=["cases"])
BenchmarkSet = Literal["v1", "audit_v1", "audit_v2"]


def _benchmark_path(benchmark_set: BenchmarkSet) -> Path:
    return Path("benchmark_sets") / benchmark_set


@router.get("")
def cases(benchmark_set: BenchmarkSet = "v1") -> list[dict[str, object]]:
    return [
        {
            "id": case.id,
            "benchmark_set": benchmark_set,
            "title": case.title,
            "category": case.category,
            "severity": case.severity,
            "stack": case.stack,
            "ground_truth_summary": case.ground_truth.primary_bug.summary,
            "validation": case.validation.model_dump(mode="json"),
            "execution": case.execution.model_dump(mode="json"),
        }
        for case in load_cases(_benchmark_path(benchmark_set))
    ]


@router.get("/{case_id}")
def case_detail(case_id: str, benchmark_set: BenchmarkSet = "v1") -> dict[str, object]:
    for case in load_cases(_benchmark_path(benchmark_set)):
        if case.id == case_id:
            context = build_context(case)
            reference_patch_path = case.case_dir / "reference.patch" if case.case_dir else None
            return {
                **case.model_dump(mode="json"),
                "benchmark_set": benchmark_set,
                "diff": context.diff,
                "relevant_files": context.relevant_files,
                "reference_patch": (
                    reference_patch_path.read_text(encoding="utf-8")
                    if reference_patch_path and reference_patch_path.exists()
                    else None
                ),
            }
    raise HTTPException(status_code=404, detail="Case not found")
