"""Optional OpenAI-backed reviewer."""

from __future__ import annotations

import os
import time

from arena.core.errors import ReviewerError
from arena.core.models import CaseContext, ReviewerResponse
from arena.reviewers.base import BaseReviewer
from arena.reviewers.prompt_templates import render_prompt
from arena.reviewers.response_parser import parse_review_response


class OpenAIReviewer(BaseReviewer):
    name = "openai"

    def __init__(self, model: str = "gpt-4.1", temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature

    def review(self, context: CaseContext) -> ReviewerResponse:
        if not os.getenv("OPENAI_API_KEY"):
            raise ReviewerError("OPENAI_API_KEY is required for the OpenAI reviewer.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ReviewerError("Install the 'openai' extra to use the OpenAI reviewer.") from exc
        prompt = render_prompt(context)
        started = time.perf_counter()
        client = OpenAI()
        completion = client.responses.create(
            model=self.model, input=prompt, temperature=self.temperature
        )
        raw = str(completion.output_text or "")

        def repair(invalid: str) -> str:
            repair_response = client.responses.create(
                model=self.model,
                input=(
                    "Repair the following response into JSON that exactly matches the requested "
                    f"schema. Return only JSON.\n\n{invalid}"
                ),
                temperature=0,
            )
            return str(repair_response.output_text or "")

        parsed, attempts = parse_review_response(raw, repair=repair)
        usage = getattr(completion, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return ReviewerResponse(
            raw_response=raw,
            parsed_response=parsed,
            invalid_output=parsed is None,
            parse_attempts=attempts,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=_estimate_cost(self.model or "gpt-4.1", input_tokens, output_tokens),
        )


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Configurable baseline estimates; update when using production billing reports."""
    pricing_per_million = {"gpt-4.1": (2.0, 8.0)}
    input_rate, output_rate = pricing_per_million.get(model, (0.0, 0.0))
    return round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 6)
