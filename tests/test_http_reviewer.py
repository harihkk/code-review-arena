"""Local HTTP / OpenAI-compatible reviewer: parsing, blinding, and error handling."""

import json

import httpx

from arena.core.models import CaseContext, ReviewerCaseMetadata
from arena.core.registry import create_reviewer
from arena.reviewers.http import HttpReviewer

VALID_REVIEW = {
    "findings": [
        {
            "title": "Tenant not scoped",
            "summary": "Cache key omits tenant.",
            "category": "security",
            "severity": "high",
            "file": "app/a.py",
            "line_start": 1,
            "line_end": 2,
            "evidence": "key built without tenant",
            "confidence": 0.9,
        }
    ],
    "proposed_patch": "--- a/app/a.py\n+++ b/app/a.py\n@@ -1 +1 @@\n-x\n+y\n",
    "overall_risk": "high",
    "review_summary": "one real bug",
}


def _context() -> CaseContext:
    return CaseContext(
        case=ReviewerCaseMetadata(
            id="c1",
            title="t",
            category="security",
            severity="high",
            stack=["python"],
            description="d",
        ),
        diff="--- a\n+++ b\n",
        relevant_files={"app/a.py": "x = 1\n"},
    )


def test_openai_style_parses_chat_completion_and_blinds_payload():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(VALID_REVIEW)}}]}
        )

    reviewer = HttpReviewer(
        "http://local/v1", style="openai", model="llama3", transport=httpx.MockTransport(handler)
    )
    response = reviewer.review(_context())

    assert response.invalid_output is False
    assert response.parsed_response is not None
    assert len(response.parsed_response.findings) == 1
    assert response.parsed_response.proposed_patch.startswith("--- a/app/a.py")
    assert captured["url"].endswith("/chat/completions")
    assert captured["body"]["model"] == "llama3"
    # The reviewer is blind: only diff/files are sent, never ground-truth fields.
    user_message = captured["body"]["messages"][1]["content"]
    assert "pr_diff" in user_message
    assert "must_mention" not in user_message


def test_json_style_parses_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=VALID_REVIEW)

    reviewer = HttpReviewer(
        "http://local/review", style="json", transport=httpx.MockTransport(handler)
    )
    response = reviewer.review(_context())
    assert response.invalid_output is False
    assert response.parsed_response is not None
    assert response.parsed_response.proposed_patch is not None


def test_http_error_becomes_invalid_output_with_summary():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server exploded")

    reviewer = HttpReviewer(
        "http://local/v1", style="openai", transport=httpx.MockTransport(handler)
    )
    response = reviewer.review(_context())
    assert response.invalid_output is True
    assert response.parsed_response is not None
    assert "failed" in response.parsed_response.review_summary


def test_malformed_chat_shape_is_invalid_output():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    reviewer = HttpReviewer(
        "http://local/v1", style="openai", transport=httpx.MockTransport(handler)
    )
    response = reviewer.review(_context())
    assert response.invalid_output is True


def test_registry_builds_http_and_openai_reviewers():
    openai = create_reviewer("openai:http://localhost:11434/v1", model="llama3")
    assert isinstance(openai, HttpReviewer)
    assert openai.style == "openai"
    assert openai.url == "http://localhost:11434/v1"
    assert openai.model == "llama3"

    plain = create_reviewer("http:http://localhost:8080/review")
    assert isinstance(plain, HttpReviewer)
    assert plain.style == "json"
    assert plain.url == "http://localhost:8080/review"
