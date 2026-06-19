"""The in-process job queue bounds its memory by evicting old finished jobs."""

from datetime import datetime, timedelta

from arena.server.jobs import Job, JobQueue


def _finished(index: int, base: datetime) -> Job:
    return Job(
        id=f"job-{index}",
        status="completed",
        submitted_at=base,
        completed_at=base + timedelta(seconds=index),
    )


def test_evicts_oldest_finished_jobs_beyond_the_cap():
    queue = JobQueue(max_finished=2)
    base = datetime(2020, 1, 1)
    for index in range(5):
        job = _finished(index, base)
        queue._jobs[job.id] = job
    queue._evict_finished_locked()
    # Only the two most recent finished jobs survive.
    assert set(queue._jobs) == {"job-3", "job-4"}


def test_eviction_never_drops_active_jobs():
    queue = JobQueue(max_finished=1)
    base = datetime(2020, 1, 1)
    queue._jobs["running"] = Job(id="running", status="running", submitted_at=base)
    queue._jobs["queued"] = Job(id="queued", status="queued", submitted_at=base)
    for index in range(3):
        job = _finished(index, base)
        queue._jobs[job.id] = job
    queue._evict_finished_locked()
    assert "running" in queue._jobs
    assert "queued" in queue._jobs
    finished_left = [j for j in queue._jobs.values() if j.status == "completed"]
    assert len(finished_left) == 1
