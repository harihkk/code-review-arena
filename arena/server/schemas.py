"""API request schemas."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    benchmark_set: Path = Path("benchmark_sets/v1")
    reviewer: str = "mock:perfect"
    model: str | None = None
    models: str | None = None
    mode: Literal["review", "patch", "full"] = "review"
    beta: float | None = None
    allow_local_execution: bool = False
