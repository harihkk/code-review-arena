"""Optional Anthropic-backed reviewer adapter."""

from __future__ import annotations

import os
import time

from arena.core.errors import ReviewerError
from arena.core.models import CaseContext, ReviewerResponse
from arena.reviewers.base import BaseReviewer
from arena.reviewers.prompt_templates import render_prompt
from arena.reviewers.response_parser import parse_review_response


class AnthropicReviewer(BaseReviewer):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        self.model = model

    def review(self, context: CaseContext) -> ReviewerResponse:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ReviewerError("ANTHROPIC_API_KEY is required for the Anthropic reviewer.")
        try:
            import anthropic
        except ImportError as exc:
            raise ReviewerError("Install the 'anthropic' extra to use this reviewer.") from exc
        started = time.perf_counter()
        message = anthropic.Anthropic().messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=0,
            messages=[{"role": "user", "content": render_prompt(context)}],
        )
        raw = "".join(block.text for block in message.content if hasattr(block, "text"))
        parsed, attempts = parse_review_response(raw)
        return ReviewerResponse(
            raw_response=raw,
            parsed_response=parsed,
            invalid_output=parsed is None,
            parse_attempts=attempts,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
