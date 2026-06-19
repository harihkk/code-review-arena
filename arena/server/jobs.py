"""In-process job queue for benchmark runs triggered over HTTP.

POST /runs used to execute a full benchmark inside the request handler. Runs
now execute on a single worker thread with a bounded pending queue: the
request returns a job id immediately, and the caller polls the job endpoint.
This keeps one slow run from monopolizing the server and gives an obvious
back-pressure signal (429) instead of stacked synchronous executions.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

JobStatus = Literal["queued", "running", "completed", "failed"]


class Job(BaseModel):
    id: str
    status: JobStatus
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    run_id: str | None = None
    error: str | None = None


class JobQueue:
    def __init__(self, max_pending: int = 4, max_finished: int = 100) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="arena-run")
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._max_pending = max_pending
        self._max_finished = max_finished

    def _evict_finished_locked(self) -> None:
        """Bound memory: keep only the most recent ``max_finished`` finished jobs.

        Active (queued/running) jobs are never evicted. Without this the job map
        would grow without bound over a long-running server's lifetime.
        """
        finished = [job for job in self._jobs.values() if job.status in {"completed", "failed"}]
        if len(finished) <= self._max_finished:
            return
        finished.sort(key=lambda job: job.completed_at or job.submitted_at)
        for job in finished[: len(finished) - self._max_finished]:
            self._jobs.pop(job.id, None)

    def submit(self, run: Callable[[], str]) -> Job | None:
        """Queue a callable returning a run_id; None when the queue is full."""
        with self._lock:
            pending = sum(1 for job in self._jobs.values() if job.status in {"queued", "running"})
            if pending >= self._max_pending:
                return None
            self._evict_finished_locked()
            job = Job(id=uuid.uuid4().hex, status="queued", submitted_at=datetime.now())
            self._jobs[job.id] = job

        def execute() -> None:
            with self._lock:
                job.status = "running"
                job.started_at = datetime.now()
            try:
                run_id = run()
            except Exception as exc:  # noqa: BLE001 - failures must land in job state.
                with self._lock:
                    job.status = "failed"
                    job.error = f"{type(exc).__name__}: {exc}"
                    job.completed_at = datetime.now()
                return
            with self._lock:
                job.status = "completed"
                job.run_id = run_id
                job.completed_at = datetime.now()

        self._executor.submit(execute)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy() if job else None


_queue: JobQueue | None = None
_queue_lock = threading.Lock()


def job_queue() -> JobQueue:
    global _queue
    with _queue_lock:
        if _queue is None:
            _queue = JobQueue()
        return _queue
