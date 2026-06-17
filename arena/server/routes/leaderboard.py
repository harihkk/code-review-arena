from fastapi import APIRouter

from arena.core.config import database_path
from arena.storage.repository import RunRepository

router = APIRouter(tags=["leaderboard"])


@router.get("/leaderboard")
def leaderboard(include_unverified: bool = False) -> list[dict[str, object]]:
    return RunRepository(database_path()).leaderboard(include_unverified=include_unverified)
