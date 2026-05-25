"""Summary series suitable for future dashboard chart components."""

from arena.core.models import RunResult


def case_score_series(run: RunResult) -> list[dict[str, object]]:
    return [{"case_id": item.case_id, "score": item.score} for item in run.case_results]
