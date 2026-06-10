"""Factory for reviewer command-line identifiers."""

from __future__ import annotations

from arena.core.errors import ReviewerError
from arena.reviewers.base import BaseReviewer
from arena.reviewers.custom_command import CustomCommandReviewer
from arena.reviewers.mock import MockReviewer
from arena.reviewers.reference_patch import ReferencePatchReviewer


def create_reviewer(
    spec: str,
    *,
    command: str | None = None,
    reviewer_timeout_seconds: int = 120,
    reveal_metadata: bool = False,
) -> BaseReviewer:
    if spec.startswith("mock"):
        mode = spec.partition(":")[2] or "perfect"
        return MockReviewer(mode)
    if spec == "reference-patch":
        return ReferencePatchReviewer()
    if spec == "custom-command":
        if not command:
            raise ReviewerError("--command is required for the custom-command reviewer.")
        return CustomCommandReviewer(command, reviewer_timeout_seconds, reveal_metadata)
    raise ReviewerError(
        f"Unknown reviewer: {spec}. "
        "Available: mock:<mode>, reference-patch, custom-command. "
        "Benchmark a real model by wiring it through custom-command."
    )
