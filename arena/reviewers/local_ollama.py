"""Local Ollama reviewer adapter."""

from __future__ import annotations

import os
import time

import httpx

from arena.core.models import CaseContext, ReviewerResponse
from arena.reviewers.base import BaseReviewer
from arena.reviewers.prompt_templates import render_prompt
from arena.reviewers.response_parser import parse_review_response


class OllamaReviewer(BaseReviewer):
    name = "ollama"

    def __init__(self, model: str = "qwen2.5-coder") -> None:
        self.model = model
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def review(self, context: CaseContext) -> ReviewerResponse:
        started = time.perf_counter()
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": render_prompt(context), "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        raw = response.json().get("response", "")
        parsed, attempts = parse_review_response(raw)
        return ReviewerResponse(
            raw_response=raw,
            parsed_response=parsed,
            invalid_output=parsed is None,
            parse_attempts=attempts,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
