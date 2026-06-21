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

from arena.core import limits
from arena.core.models import CaseContext, ReviewerResponse
from arena.reviewers.base import BaseReviewer
from arena.reviewers.custom_command import serialize_reviewer_case
from arena.reviewers.response_parser import parse_reviewer_output, response_from_outcome
from arena.reviewers.strict_json import StrictJSONError, strict_loads

# Bound for the message recorded on an invalid HTTP reviewer response (well under
# the strict ReviewResult.review_summary cap, and never includes request headers).
_INVALID_MESSAGE_LEN = 4096

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

    def _post_bounded(self, payload: dict[str, object]) -> tuple[bytes, int, bool]:
        """Stream the response, returning (body, status, too_large).

        The body is read in chunks and capped at ``RAW_RESPONSE_BYTES + 1`` so a
        huge or never-ending response is never fully materialized. ``iter_bytes``
        yields content-decoded bytes, so the cap is enforced on the DECODED body
        that will actually be parsed and a compressed bomb cannot bypass it.
        Content-Length is NOT consulted: it describes the transferred (encoded)
        representation and can be absent or false, so the streamed decoded-byte
        count is authoritative. On overflow the stream context closes the response.
        """
        limit = limits.RAW_RESPONSE_BYTES
        with httpx.Client(timeout=self.timeout_seconds, transport=self._transport) as client:
            with client.stream(
                "POST",
                self._endpoint(),
                json=self._request_body(payload),
                headers=self._headers(),
            ) as response:
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > limit:
                        return b"", response.status_code, True
                    chunks.append(chunk)
                return b"".join(chunks), response.status_code, False

    def review(self, context: CaseContext) -> ReviewerResponse:
        started = time.perf_counter()
        payload = serialize_reviewer_case(
            context,
            reveal_metadata=self.reveal_metadata,
            reveal_test_output=self.reveal_test_output,
        )
        try:
            body, status, too_large = self._post_bounded(payload)
        except httpx.HTTPError as exc:
            return self._error_response(exc, started)
        if too_large:
            return self._invalid("reviewer_output_too_large", started)
        if status >= 400:
            # A non-2xx body is only a diagnostic snippet, never parsed as reviewer
            # JSON, so bounded replacement decoding is acceptable here.
            snippet = body.decode("utf-8", errors="replace")[:512]
            return self._invalid(
                f"http reviewer request failed with status {status}: {snippet}", started
            )
        # A successful body is decoded STRICTLY: invalid UTF-8 cannot be silently
        # repaired with replacement characters into a parseable review.
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            return self._invalid("http reviewer response was not valid UTF-8", started)
        # The OpenAI outer envelope goes through the same strict JSON decoder (so
        # duplicate keys / non-finite constants there also fail); its assistant
        # content is then parsed by the shared reviewer parser. Plain JSON style
        # passes the whole body through the same parser.
        if self.style == "openai":
            try:
                content = self._extract_openai_content(strict_loads(text))
            except (StrictJSONError, KeyError, IndexError, TypeError) as exc:
                return self._invalid(f"malformed OpenAI envelope: {type(exc).__name__}", started)
        else:
            content = text
        outcome = parse_reviewer_output(content, enable_repair=self.enable_repair)
        return response_from_outcome(
            outcome, raw=content, latency_ms=int((time.perf_counter() - started) * 1000)
        )

    def _error_response(self, exc: Exception, started: float) -> ReviewerResponse:
        return self._invalid(f"http reviewer request failed: {type(exc).__name__}: {exc}", started)

    def _invalid(self, message: str, started: float) -> ReviewerResponse:
        # The recorded message is bounded and derived only from status/exception
        # type and body text, never from request headers, so no secret is persisted.
        bounded = message[:_INVALID_MESSAGE_LEN]
        return ReviewerResponse(
            raw_response=json.dumps({"error": bounded}),
            parsed_response=None,
            invalid_output=True,
            parse_attempts=1,
            parse_status="invalid",
            parse_error_summary=bounded,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
