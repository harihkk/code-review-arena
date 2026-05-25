"""Factory for reviewer command-line identifiers."""

from __future__ import annotations

from arena.core.errors import ReviewerError
from arena.reviewers.anthropic import AnthropicReviewer
from arena.reviewers.base import BaseReviewer
from arena.reviewers.custom_command import CustomCommandReviewer
from arena.reviewers.ensemble import EnsembleReviewer
from arena.reviewers.gemini import GeminiReviewer
from arena.reviewers.local_ollama import OllamaReviewer
from arena.reviewers.mock import MockReviewer
from arena.reviewers.openai import OpenAIReviewer
from arena.reviewers.reference_patch import ReferencePatchReviewer


def create_reviewer(
    spec: str,
    model: str | None = None,
    models: str | None = None,
    *,
    command: str | None = None,
    reviewer_timeout_seconds: int = 120,
) -> BaseReviewer:
    if spec.startswith("mock"):
        mode = spec.partition(":")[2] or "perfect"
        return MockReviewer(mode)
    if spec == "reference-patch":
        return ReferencePatchReviewer()
    if spec == "openai":
        return OpenAIReviewer(model or "gpt-4.1")
    if spec == "anthropic":
        return AnthropicReviewer(model or "claude-sonnet-4-20250514")
    if spec == "gemini":
        return GeminiReviewer(model or "gemini-2.5-pro")
    if spec in {"ollama", "local_ollama"}:
        return OllamaReviewer(model or "qwen2.5-coder")
    if spec == "ensemble":
        if not models:
            raise ReviewerError("--models is required for an ensemble reviewer.")
        reviewers = []
        for item in models.split(","):
            provider, _, provider_model = item.partition(":")
            reviewers.append(create_reviewer(provider, provider_model or None))
        return EnsembleReviewer(reviewers)
    if spec == "custom-command":
        if not command:
            raise ReviewerError("--command is required for custom-command reviewer.")
        return CustomCommandReviewer(command, reviewer_timeout_seconds)
    raise ReviewerError(f"Unknown reviewer: {spec}")
