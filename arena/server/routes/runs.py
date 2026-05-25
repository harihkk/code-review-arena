from fastapi import APIRouter, HTTPException

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.case_loader import build_context, load_cases
from arena.core.config import DEFAULT_BENCHMARK_SET, database_path
from arena.core.registry import create_reviewer
from arena.server.schemas import CreateRunRequest
from arena.storage.repository import RunRepository

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def runs() -> list[dict[str, object]]:
    return RunRepository(database_path()).list_runs()


@router.post("")
def create_run(request: CreateRunRequest) -> dict[str, object]:
    reviewer = create_reviewer(request.reviewer, request.model, request.models)
    return run_benchmark(
        request.benchmark_set,
        reviewer,
        mode=request.mode,
        beta=request.beta,
        allow_local_execution=request.allow_local_execution,
    ).model_dump(mode="json")


@router.get("/{run_id}")
def run_detail(run_id: str) -> dict[str, object]:
    run = RunRepository(database_path()).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.model_dump(mode="json")


@router.get("/{run_id}/cases/{case_id}")
def run_case_detail(run_id: str, case_id: str) -> dict[str, object]:
    run = RunRepository(database_path()).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    for result in run.case_results:
        if result.case_id == case_id:
            for case in load_cases(DEFAULT_BENCHMARK_SET):
                if case.id == case_id:
                    context = build_context(case)
                    return {
                        **result.model_dump(mode="json"),
                        "diff": context.diff,
                        "ground_truth": case.ground_truth.model_dump(mode="json"),
                        "stack": case.stack,
                    }
            return result.model_dump(mode="json")
    raise HTTPException(status_code=404, detail="Case result not found")
