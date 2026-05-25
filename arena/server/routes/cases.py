from fastapi import APIRouter, HTTPException

from arena.benchmark.case_loader import build_context, load_cases
from arena.core.config import DEFAULT_BENCHMARK_SET

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
def cases() -> list[dict[str, object]]:
    return [
        {
            "id": case.id,
            "title": case.title,
            "category": case.category,
            "severity": case.severity,
            "stack": case.stack,
            "ground_truth_summary": case.ground_truth.primary_bug.summary,
            "validation": case.validation.model_dump(mode="json"),
            "execution": case.execution.model_dump(mode="json"),
        }
        for case in load_cases(DEFAULT_BENCHMARK_SET)
    ]


@router.get("/{case_id}")
def case_detail(case_id: str) -> dict[str, object]:
    for case in load_cases(DEFAULT_BENCHMARK_SET):
        if case.id == case_id:
            context = build_context(case)
            return {
                **case.model_dump(mode="json"),
                "diff": context.diff,
                "relevant_files": context.relevant_files,
            }
    raise HTTPException(status_code=404, detail="Case not found")
