from fastapi import APIRouter, Depends, HTTPException

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.case_loader import build_context, load_cases
from arena.core.config import benchmark_root, database_path, resolve_benchmark_set
from arena.core.errors import ReviewerError
from arena.core.registry import create_reviewer
from arena.server.auth import require_api_token, server_local_execution_enabled
from arena.server.jobs import job_queue
from arena.server.schemas import CreateRunRequest
from arena.storage.repository import RunRepository

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def runs() -> list[dict[str, object]]:
    return RunRepository(database_path()).list_runs()


def _normalize_benchmark_set(value: str) -> str:
    root_prefix = benchmark_root().as_posix().rstrip("/") + "/"
    if value.startswith(root_prefix):
        return value[len(root_prefix) :]
    return value


@router.post("", status_code=202, dependencies=[Depends(require_api_token)])
def create_run(request: CreateRunRequest) -> dict[str, object]:
    benchmark_dir = resolve_benchmark_set(_normalize_benchmark_set(request.benchmark_set))
    if benchmark_dir is None:
        raise HTTPException(status_code=400, detail="Unknown benchmark set")
    if request.allow_local_execution and not server_local_execution_enabled():
        raise HTTPException(
            status_code=403,
            detail="Local execution over HTTP is disabled; set "
            "ARENA_SERVER_ALLOW_LOCAL_EXECUTION=1 on the server to opt in.",
        )
    try:
        reviewer = create_reviewer(request.reviewer, command=request.command)
    except ReviewerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    def execute() -> str:
        return run_benchmark(
            benchmark_dir,
            reviewer,
            mode=request.mode,
            beta=request.beta,
            allow_local_execution=request.allow_local_execution,
        ).run_id

    job = job_queue().submit(execute)
    if job is None:
        raise HTTPException(status_code=429, detail="Run queue is full; retry later")
    return {"job_id": job.id, "status": job.status, "status_url": f"/runs/jobs/{job.id}"}


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    job = job_queue().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump(mode="json")


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
            benchmark_dir = resolve_benchmark_set(run.benchmark_set)
            if benchmark_dir is None:
                return result.model_dump(mode="json")
            for case in load_cases(benchmark_dir):
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
