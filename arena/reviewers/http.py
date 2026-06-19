"""Review a case via a local HTTP endpoint (OpenAI-compatible or plain JSON).

This keeps Arena provider-neutral and fully local: point it at Ollama, LM Studio,
vLLM, llama.cpp, or any OpenAI-compatible server -- no paid SDK required. Two
styles are supported:

- "openai": POST {base_url}/chat/completions and parse the assistant message as
  the ReviewResult contract JSON.
- "json": POST the blind reviewer payload directly and parse the response body
  as ReviewResult JSON.

The reviewer never receives ground truth: it only ever sends the blinded
serialize_reviewer_case() payload, exactly like the command reviewer. Pre-patch
test output is excluded unless the caller opts into the test-assisted mode.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Literal

import httpx

from arena.core.models import CaseContext, ReviewerResponse, ReviewResult
from arena.reviewers.base import BaseReviewer
from arena.reviewers.custom_command import serialize_reviewer_case
from arena.reviewers.response_parser import naive_repair, parse_review_response

SYSTEM_PROMPT = (
    "You are a code reviewer under evaluation. Inspect the pull request diff and "
    "files, then return ONLY one JSON object with this shape:\n"
    '{"findings": [{"title": str, "summary": str, "category": str, '
    '"severity": "critical|high|medium|low", "file": str, "line_start": int, '
    '"line_end": int, "evidence": str, "confidence": number 0..1, '
    '"suggested_fix": str or null}], '
    '"proposed_patch": "one complete unified diff repairing the whole case, or null", '
    '"overall_risk": "critical|high|medium|low|none", "review_summary": str}\n'
    "Emit no prose outside the JSON. proposed_patch is the single repair Arena "
    "applies; per-finding patches are never applied."
)

HttpStyle = Literal["openai", "json"]


class HttpReviewer(BaseReviewer):
    name = "http"

    def __init__(
        self,
        url: str,
        *,
        style: HttpStyle = "openai",
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 120,
        reveal_metadata: bool = False,
        enable_repair: bool = False,
        reveal_test_output: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.style: HttpStyle = style
        # Local servers usually ignore the model name, but Ollama/vLLM/LM Studio
        # require it; ARENA_HTTP_MODEL is the keyless local-first default.
        self.model = model or os.getenv("ARENA_HTTP_MODEL") or "default"
        self.api_key = api_key or os.getenv("ARENA_HTTP_API_KEY")
        self.timeout_seconds = timeout_seconds
        self.reveal_metadata = reveal_metadata
        self.enable_repair = enable_repair
        self.reveal_test_output = reveal_test_output
        self._transport = transport

    def safe_config(self) -> dict[str, object]:
        return {
            "url": self.url,
            "style": self.style,
            "model": self.model,
            "api_key_set": self.api_key is not None,
            "timeout_seconds": self.timeout_seconds,
            "reveal_metadata": self.reveal_metadata,
            "enable_repair": self.enable_repair,
            "reveal_test_output": self.reveal_test_output,
        }

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _endpoint(self) -> str:
        if self.style == "openai" and not self.url.endswith("/chat/completions"):
            return f"{self.url}/chat/completions"
        return self.url

    def _request_body(self, payload: dict[str, object]) -> dict[str, object]:
        if self.style == "openai":
            return {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload)},
                ],
            }
        return payload

    @staticmethod
    def _extract_openai_content(data: Any) -> str:
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("chat completion message content is not a string")
        return content

    def review(self, context: CaseContext) -> ReviewerResponse:
        started = time.perf_counter()
        payload = serialize_reviewer_case(
            context,
            reveal_metadata=self.reveal_metadata,
            reveal_test_output=self.reveal_test_output,
        )
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
                response = client.post(
                    self._endpoint(),
                    json=self._request_body(payload),
                    headers=self._headers(),
                )
            response.raise_for_status()
            raw = (
                self._extract_openai_content(response.json())
                if self.style == "openai"
                else response.text
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            return self._error_response(exc, started)
        parsed, attempts = parse_review_response(
            raw or "{}", repair=naive_repair if self.enable_repair else None
        )
        return ReviewerResponse(
            raw_response=raw or "",
            parsed_response=parsed,
            invalid_output=parsed is None or not raw,
            parse_attempts=attempts,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _error_response(self, exc: Exception, started: float) -> ReviewerResponse:
        message = f"http reviewer request failed: {type(exc).__name__}: {exc}"
        return ReviewerResponse(
            raw_response=json.dumps({"error": message}),
            parsed_response=ReviewResult(findings=[], overall_risk="none", review_summary=message),
            invalid_output=True,
            parse_attempts=1,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
