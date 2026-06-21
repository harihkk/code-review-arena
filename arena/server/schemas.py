"""API request schemas."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from arena.core import limits


class CreateRunRequest(BaseModel):
    # Strict, bounded API input: forbid unknown keys, reject string-to-number and
    # string-to-boolean coercion, validate defaults, reject NaN/inf. FastAPI keeps
    # the field-location errors in its 422 response.
    model_config = ConfigDict(
        extra="forbid", strict=True, validate_default=True, allow_inf_nan=False
    )

    # A pack name under the configured benchmark root. A legacy
    # "benchmark_sets/<name>" path is accepted and normalized to <name>.
    benchmark_set: Annotated[
        str, StringConstraints(min_length=1, max_length=limits.BENCHMARK_SET_NAME_LEN)
    ] = "v1"
    reviewer: Annotated[str, StringConstraints(min_length=1, max_length=limits.REVIEWER_ID_LEN)] = (
        "control:perfect"
    )
    command: Annotated[str, StringConstraints(max_length=limits.COMMAND_LEN)] | None = None
    mode: Literal["review", "patch", "full"] = "review"
    beta: float | None = Field(default=None, gt=0, le=limits.LINE_NUMBER_MAX)
    allow_local_execution: bool = False
    max_wall_seconds: float | None = Field(default=None, gt=0)
    max_cost: float | None = Field(default=None, ge=0)
