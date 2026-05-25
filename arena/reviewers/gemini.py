"""Optional Gemini-backed reviewer adapter."""

from __future__ import annotations

import os
import time

from arena.core.errors import ReviewerError
from arena.core.models import CaseContext, ReviewerResponse
from arena.reviewers.base import BaseReviewer
from arena.reviewers.prompt_templates import render_prompt
from arena.reviewers.response_parser import parse_review_response


class GeminiReviewer(BaseReviewer):
    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-pro") -> None:
        self.model = model

    def review(self, context: CaseContext) -> ReviewerResponse:
        if not os.getenv("GEMINI_API_KEY"):
            raise ReviewerError("GEMINI_API_KEY is required for the Gemini reviewer.")
        try:
            from google import genai
        except ImportError as exc:
            raise ReviewerError("Install the 'gemini' extra to use this reviewer.") from exc
        started = time.perf_counter()
        response = genai.Client(api_key=os.environ["GEMINI_API_KEY"]).models.generate_content(
            model=self.model,
            contents=render_prompt(context),
        )
        raw = response.text or ""
        parsed, attempts = parse_review_response(raw)
        return ReviewerResponse(
            raw_response=raw,
            parsed_response=parsed,
            invalid_output=parsed is None,
            parse_attempts=attempts,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
