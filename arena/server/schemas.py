"""API request schemas."""

from typing import Literal

from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    # A pack name under the configured benchmark root. A legacy
    # "benchmark_sets/<name>" path is accepted and normalized to <name>.
    benchmark_set: str = "v1"
    reviewer: str = "mock:perfect"
    command: str | None = None
    mode: Literal["review", "patch", "full"] = "review"
    beta: float | None = None
    allow_local_execution: bool = False
