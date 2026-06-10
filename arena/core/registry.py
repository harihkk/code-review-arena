"""Factory for reviewer command-line identifiers."""

from __future__ import annotations

import sys

from arena.core.errors import ReviewerError
from arena.reviewers.base import BaseReviewer
from arena.reviewers.controls import ControlReviewer
from arena.reviewers.custom_command import CustomCommandReviewer
from arena.reviewers.reference_patch import ReferencePatchReviewer


def create_reviewer(
    spec: str,
    *,
    command: str | None = None,
    reviewer_timeout_seconds: int = 120,
    reveal_metadata: bool = False,
    enable_repair: bool = False,
) -> BaseReviewer:
    if spec in {"reference-patch", "control:reference_patch"}:
        return ReferencePatchReviewer()
    if spec.startswith("control"):
        mode = spec.partition(":")[2] or "perfect"
        return ControlReviewer(mode)
    if spec.startswith("mock"):
        print(
            "DEPRECATED: the mock:* reviewer spec is renamed control:*; "
            "the alias will be removed in a future release.",
            file=sys.stderr,
        )
        mode = spec.partition(":")[2] or "perfect"
        return ControlReviewer(mode)
    if spec == "custom-command":
        if not command:
            raise ReviewerError("--command is required for the custom-command reviewer.")
        return CustomCommandReviewer(
            command, reviewer_timeout_seconds, reveal_metadata, enable_repair
        )
    raise ReviewerError(
        f"Unknown reviewer: {spec}. "
        "Available: control:<mode> (deprecated alias mock:<mode>), reference-patch, "
        "custom-command. Benchmark a real model by wiring it through custom-command."
    )
