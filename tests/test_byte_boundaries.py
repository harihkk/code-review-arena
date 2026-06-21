"""Phase 1B commit 2: pre-parse byte boundaries for files, HTTP, commands, API.

These cover the bounded reader and every boundary the harness enforces before
parsing: pack files, diffs, reference patches, YAML (alias/mapping), HTTP reviewer
responses, custom-command output, and the API request body. Limits are operational
safety bounds, not correctness claims.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import stat

import httpx
import pytest

from arena.benchmark.artifacts import load_reference_patch
from arena.benchmark.case_loader import load_case, load_manifest
from arena.benchmark.diff_loader import load_diff
from arena.core import limits
from arena.core.bounded_io import (
    read_bytes_bounded,
    read_text_bounded,
    read_text_capped,
    read_yaml_mapping_bounded,
)
from arena.core.errors import (
    InputTooLargeError,
    InvalidEncodingError,
    UnsafeInputError,
    ValidationError,
)
from arena.core.models import CaseContext, ReviewerCaseMetadata
from arena.execution.process import SupervisedResult
from arena.reviewers import custom_command as cc_module
from arena.reviewers.custom_command import CustomCommandReviewer
from arena.reviewers.http import HttpReviewer
from arena.server.middleware import _TOO_LARGE_BODY, BodySizeLimitMiddleware

# --------------------------------------------------------------------------- #
# Bounded reader: exact/over, encoding, type, byte-vs-char counting           #
# --------------------------------------------------------------------------- #


def test_read_bytes_exact_limit_accepted_one_over_rejected(tmp_path):
    path = tmp_path / "f.bin"
    path.write_bytes(b"a" * 10)
    assert read_bytes_bounded(path, 10, label="f") == b"a" * 10  # exact
    with pytest.raises(InputTooLargeError):
        read_bytes_bounded(path, 9, label="f")  # one over the limit


def test_read_text_counts_bytes_not_characters(tmp_path):
    path = tmp_path / "m.txt"
    path.write_bytes(("é" * 5).encode("utf-8"))  # 5 chars, 10 UTF-8 bytes
    assert read_text_bounded(path, 10, label="m") == "é" * 5  # exact at 10 bytes
    with pytest.raises(InputTooLargeError):
        read_text_bounded(path, 9, label="m")  # 10 bytes > 9, though only 5 chars


def test_invalid_utf8_distinguished_from_too_large(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\xff\xfe\xfa")
    # bytes read fine; only the strict decode rejects, with a distinct type
    assert read_bytes_bounded(path, 10, label="b") == b"\xff\xfe\xfa"
    with pytest.raises(InvalidEncodingError):
        read_text_bounded(path, 10, label="b")


def test_missing_file_is_distinct_from_unsafe(tmp_path):
    with pytest.raises(ValidationError) as exc:
        read_text_bounded(tmp_path / "nope.txt", 10, label="x")
    assert "missing" in str(exc.value)
    assert not isinstance(exc.value, (InputTooLargeError, UnsafeInputError, InvalidEncodingError))


def test_symlink_rejected(tmp_path):
    target = tmp_path / "real.txt"
    target.write_text("hi")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    with pytest.raises(UnsafeInputError):
        read_text_bounded(link, 100, label="link")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no mkfifo on this platform")
def test_non_regular_file_rejected(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert stat.S_ISFIFO(fifo.lstat().st_mode)
    with pytest.raises(UnsafeInputError):
        read_bytes_bounded(fifo, 100, label="fifo")


def test_capped_reader_truncates_instead_of_rejecting(tmp_path):
    path = tmp_path / "src.py"
    path.write_bytes(b"a" * 100)
    text, truncated = read_text_capped(path, 10, label="src")
    assert text == "a" * 10 and truncated is True
    text, truncated = read_text_capped(path, 100, label="src")
    assert text == "a" * 100 and truncated is False


# --------------------------------------------------------------------------- #
# YAML: alias amplification and non-mapping roots                             #
# --------------------------------------------------------------------------- #


def test_yaml_alias_expansion_rejected_before_expanding(tmp_path):
    # A small billion-laughs document: each level references the one below via an
    # alias. It must be rejected at parse time, before the expanded structure
    # could be built.
    path = tmp_path / "bomb.yaml"
    path.write_text(
        "a: &a [x, x, x, x, x]\n"
        "b: &b [*a, *a, *a, *a, *a]\n"
        "c: &c [*b, *b, *b, *b, *b]\n"
        "d: [*c, *c, *c, *c, *c]\n"
    )
    with pytest.raises(ValidationError) as exc:
        read_yaml_mapping_bounded(path, limits.CASE_YAML_BYTES, label="case.yaml")
    assert "alias" in str(exc.value).lower()


def test_yaml_non_mapping_root_rejected(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- one\n- two\n")
    with pytest.raises(ValidationError) as exc:
        read_yaml_mapping_bounded(path, 1000, label="case.yaml")
    assert "mapping" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# Loaders: manifest / case / diff / reference patch                           #
# --------------------------------------------------------------------------- #


def test_manifest_loader_rejects_oversized_invalid_utf8_and_symlink(tmp_path):
    # oversized (rejected before YAML parse)
    big = tmp_path / "big"
    big.mkdir()
    (big / "manifest.yaml").write_bytes(b"# " + b"a" * limits.MANIFEST_BYTES)
    with pytest.raises(InputTooLargeError):
        load_manifest(big)
    # invalid UTF-8
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "manifest.yaml").write_bytes(b"\xff\xfe")
    with pytest.raises(InvalidEncodingError):
        load_manifest(bad)
    # symlinked manifest
    link_dir = tmp_path / "linked"
    link_dir.mkdir()
    real = tmp_path / "src.yaml"
    real.write_text("name: x\ncases: []\n")
    (link_dir / "manifest.yaml").symlink_to(real)
    with pytest.raises(UnsafeInputError):
        load_manifest(link_dir)


def test_case_loader_rejects_oversized_case_yaml(tmp_path):
    case_dir = tmp_path / "c"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_bytes(b"# " + b"a" * limits.CASE_YAML_BYTES)
    with pytest.raises(InputTooLargeError):
        load_case(case_dir)


def test_diff_loader_exact_and_over(tmp_path):
    exact = tmp_path / "ok.diff"
    exact.write_bytes(b"d" * limits.DIFF_BYTES)
    assert len(load_diff(exact)) == limits.DIFF_BYTES  # exact accepted
    over = tmp_path / "big.diff"
    over.write_bytes(b"d" * (limits.DIFF_BYTES + 1))
    with pytest.raises(InputTooLargeError):
        load_diff(over)
    # missing-file error preserved (and distinct from too-large)
    with pytest.raises(ValidationError) as exc:
        load_diff(tmp_path / "missing.diff")
    assert "Missing pull request diff" in str(exc.value)


def test_reference_patch_loader_exact_and_over(tmp_path):
    exact = tmp_path / "ref.patch"
    exact.write_bytes(b"p" * limits.PATCH_BYTES)
    assert len(load_reference_patch(exact)) == limits.PATCH_BYTES
    over = tmp_path / "big.patch"
    over.write_bytes(b"p" * (limits.PATCH_BYTES + 1))
    with pytest.raises(InputTooLargeError):
        load_reference_patch(over)


# --------------------------------------------------------------------------- #
# HTTP reviewer: bounded streaming                                            #
# --------------------------------------------------------------------------- #

_VALID = {"findings": [], "overall_risk": "none", "review_summary": "x"}


def _json_reviewer(handler):
    return HttpReviewer("http://local/r", style="json", transport=httpx.MockTransport(handler))


def _at_limit_json(extra: int) -> bytes:
    base = json.dumps(_VALID)
    pad = limits.RAW_RESPONSE_BYTES - len(base) + extra
    return (base + " " * pad).encode("utf-8")


def test_http_response_exact_limit_accepted():
    body = _at_limit_json(0)
    assert len(body) == limits.RAW_RESPONSE_BYTES
    resp = _json_reviewer(lambda req: httpx.Response(200, content=body)).review(_ctx())
    assert resp.invalid_output is False
    assert resp.parsed_response is not None


def test_http_response_one_over_limit_rejected_without_parsing():
    # Valid JSON prefix then padding pushes one byte over: must NOT parse, must be
    # flagged as too-large rather than as a successful review.
    body = _at_limit_json(1)
    resp = _json_reviewer(lambda req: httpx.Response(200, content=body)).review(_ctx())
    assert resp.invalid_output is True
    assert resp.parsed_response.review_summary == "reviewer_output_too_large"


def test_http_oversized_without_content_length_still_rejected():
    # Streamed chunks, no Content-Length: the streamed count is authoritative.
    chunks = [b"a" * (1024 * 1024)] * 3  # 3 MB > 2 MB cap

    def handler(req):
        return httpx.Response(200, content=iter(chunks))

    resp = _json_reviewer(handler).review(_ctx())
    assert resp.invalid_output is True
    assert resp.parsed_response.review_summary == "reviewer_output_too_large"


def test_http_multi_chunk_within_limit_reassembled():
    payload = json.dumps(_VALID).encode("utf-8")
    mid = len(payload) // 2
    chunks = [payload[:mid], payload[mid:]]

    def handler(req):
        return httpx.Response(200, content=iter(chunks))  # chunked, no Content-Length

    resp = _json_reviewer(handler).review(_ctx())
    assert resp.invalid_output is False
    assert resp.parsed_response is not None


def test_http_oversized_non_2xx_body_is_bounded():
    body = b"e" * (limits.RAW_RESPONSE_BYTES + 1)
    resp = _json_reviewer(lambda req: httpx.Response(500, content=body)).review(_ctx())
    assert resp.invalid_output is True
    assert resp.parsed_response.review_summary == "reviewer_output_too_large"


def test_http_small_non_2xx_body_is_invalid_with_summary():
    resp = HttpReviewer(
        "http://local/v1",
        style="openai",
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")),
    ).review(_ctx())
    assert resp.invalid_output is True
    assert "failed" in resp.parsed_response.review_summary


def test_http_malformed_openai_envelope_is_invalid():
    resp = HttpReviewer(
        "http://local/v1",
        style="openai",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": []})),
    ).review(_ctx())
    assert resp.invalid_output is True


def test_http_plain_json_style_valid():
    resp = _json_reviewer(lambda req: httpx.Response(200, json=_VALID)).review(_ctx())
    assert resp.invalid_output is False


def _ctx() -> CaseContext:
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


# --------------------------------------------------------------------------- #
# Custom-command reviewer: output_limit_exceeded                              #
# --------------------------------------------------------------------------- #


def _supervised(stdout="", stderr="", returncode=0, exceeded=False):
    return SupervisedResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
        output_limit_exceeded=exceeded,
    )


def _patch_supervisor(monkeypatch, result):
    monkeypatch.setattr(cc_module, "run_supervised", lambda *a, **k: result)


def test_command_output_at_cap_parses_normally(monkeypatch):
    _patch_supervisor(monkeypatch, _supervised(stdout=json.dumps(_VALID), exceeded=False))
    resp = CustomCommandReviewer("echo {case_json}").review(_ctx())
    assert resp.invalid_output is False
    assert resp.parsed_response is not None


@pytest.mark.parametrize(
    "result",
    [
        _supervised(stdout=json.dumps(_VALID), exceeded=True),  # valid JSON prefix then flood
        _supervised(stdout="", stderr="E" * 1000, exceeded=True),  # stderr flood
        _supervised(stdout="{partial", stderr="more", exceeded=True),  # combined overflow
    ],
)
def test_command_overflow_is_too_large_not_malformed(monkeypatch, result):
    _patch_supervisor(monkeypatch, result)
    resp = CustomCommandReviewer("echo {case_json}").review(_ctx())
    assert resp.invalid_output is True
    assert resp.parsed_response.review_summary == "reviewer_output_too_large"


def test_command_overflow_does_not_invoke_parser(monkeypatch):
    _patch_supervisor(monkeypatch, _supervised(stdout=json.dumps(_VALID), exceeded=True))

    def explode(*a, **k):
        raise AssertionError("parser must not run after overflow")

    monkeypatch.setattr(cc_module, "parse_review_response", explode)
    resp = CustomCommandReviewer("echo {case_json}").review(_ctx())
    assert resp.invalid_output is True
    assert resp.parsed_response.review_summary == "reviewer_output_too_large"


# --------------------------------------------------------------------------- #
# API request body: pure ASGI middleware                                      #
# --------------------------------------------------------------------------- #


def _run_mw(max_bytes, method, chunks, content_length=None):
    """Drive the middleware over a crafted ASGI request; return (sent, app_state)."""
    state: dict = {"called": False, "body": None}

    async def app(scope, receive, send):
        state["called"] = True
        body = b""
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        state["body"] = body
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = BodySizeLimitMiddleware(app, max_bytes=max_bytes)
    headers = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode()))
    scope = {"type": "http", "method": method, "headers": headers}

    messages = list(chunks)
    iterator = iter(messages)
    sent: list = []

    async def receive():
        return next(iterator)

    async def send(message):
        sent.append(message)

    asyncio.run(mw(scope, receive, send))
    return sent, state


def _chunk(body, more=False):
    return {"type": "http.request", "body": body, "more_body": more}


def _status(sent):
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def test_api_body_exact_limit_accepted_one_over_rejected():
    sent, state = _run_mw(10, "POST", [_chunk(b"x" * 10)])
    assert state["called"] is True and state["body"] == b"x" * 10
    sent, state = _run_mw(10, "POST", [_chunk(b"x" * 11)])
    assert state["called"] is False and _status(sent) == 413


def test_api_chunked_body_counted_across_chunks():
    sent, state = _run_mw(10, "POST", [_chunk(b"xxxxx", more=True), _chunk(b"yyyyy")])
    assert state["called"] is True and state["body"] == b"xxxxxyyyyy"
    sent, state = _run_mw(10, "POST", [_chunk(b"xxxxx", more=True), _chunk(b"yyyyyy")])
    assert state["called"] is False and _status(sent) == 413


def test_api_content_length_not_authoritative():
    # understated CL but oversized body -> rejected by count
    sent, state = _run_mw(10, "POST", [_chunk(b"x" * 11)], content_length=1)
    assert state["called"] is False and _status(sent) == 413
    # overstated CL but small body -> accepted (CL is not trusted to reject)
    sent, state = _run_mw(10, "POST", [_chunk(b"x" * 5)], content_length=9999)
    assert state["called"] is True and state["body"] == b"x" * 5
    # missing CL, oversized body -> rejected
    sent, state = _run_mw(10, "POST", [_chunk(b"x" * 11)], content_length=None)
    assert state["called"] is False and _status(sent) == 413


def test_api_multibyte_body_counted_by_bytes():
    body = "é".encode() * 5  # 10 bytes
    sent, state = _run_mw(10, "POST", [_chunk(body)])
    assert state["called"] is True
    sent, state = _run_mw(10, "POST", [_chunk(body + b"\x00")])  # 11 bytes
    assert state["called"] is False and _status(sent) == 413


def test_api_get_requests_unaffected():
    sent, state = _run_mw(10, "GET", [_chunk(b"x" * 100)])
    assert state["called"] is True  # not bounded, not rejected


def test_api_413_response_is_small_and_stable():
    sent, _ = _run_mw(10, "POST", [_chunk(b"x" * 11)])
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = next(m for m in sent if m["type"] == "http.response.body")
    assert start["status"] == 413
    assert (b"content-type", b"application/json") in start["headers"]
    assert body["body"] == _TOO_LARGE_BODY
    assert b"Traceback" not in body["body"]


# --- Integration through the real app (single-chunk TestClient path) --------- #


def test_app_health_unaffected_and_oversized_rejected_and_malformed_422():
    from fastapi.testclient import TestClient

    from arena.server.main import app

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    # oversized body -> 413 before the route runs
    big = client.post(
        "/runs",
        content=b"x" * (limits.API_REQUEST_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert big.status_code == 413
    assert big.json()["detail"]
    # malformed JSON within the limit -> FastAPI's normal 422, not 413
    bad = client.post("/runs", content=b"{", headers={"content-type": "application/json"})
    assert bad.status_code == 422


# --------------------------------------------------------------------------- #
# YAML structure hardening: duplicate keys, depth, node count                 #
# --------------------------------------------------------------------------- #


def test_yaml_small_valid_document_accepted(tmp_path):
    path = tmp_path / "ok.yaml"
    path.write_text("a: 1\nb:\n  c: 2\n")
    assert read_yaml_mapping_bounded(path, 1000, label="case.yaml") == {"a": 1, "b": {"c": 2}}


def test_yaml_duplicate_top_level_key_rejected(tmp_path):
    path = tmp_path / "dup.yaml"
    path.write_text("a: 1\na: 2\n")
    with pytest.raises(ValidationError):
        read_yaml_mapping_bounded(path, 1000, label="case.yaml")


def test_yaml_duplicate_nested_key_rejected(tmp_path):
    path = tmp_path / "nested.yaml"
    path.write_text("outer:\n  k: 1\n  k: 2\n")
    with pytest.raises(ValidationError):
        read_yaml_mapping_bounded(path, 1000, label="case.yaml")


def test_yaml_error_does_not_leak_input_content(tmp_path):
    path = tmp_path / "secret.yaml"
    path.write_text("supersecretkey: 1\nsupersecretkey: 2\n")
    with pytest.raises(ValidationError) as exc:
        read_yaml_mapping_bounded(path, 1000, label="case.yaml")
    assert "supersecretkey" not in str(exc.value)


def test_yaml_node_count_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "YAML_MAX_NODES", 10)
    # {"root": [k ints]} composes to k + 3 nodes (map, key, list, k scalars).
    at_limit = tmp_path / "ok.yaml"
    at_limit.write_text("root: [" + ", ".join(["0"] * 7) + "]\n")  # 10 nodes
    read_yaml_mapping_bounded(at_limit, 100_000, label="case.yaml")
    over = tmp_path / "over.yaml"
    over.write_text("root: [" + ", ".join(["0"] * 8) + "]\n")  # 11 nodes
    with pytest.raises(ValidationError):
        read_yaml_mapping_bounded(over, 100_000, label="case.yaml")


def test_yaml_depth_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(limits, "YAML_MAX_DEPTH", 8)
    # "root: [[...]]" with b nested flow lists composes to depth b + 2 at the scalar.
    at_limit = tmp_path / "ok.yaml"
    at_limit.write_text("root: " + "[" * 6 + "0" + "]" * 6 + "\n")  # depth 8
    read_yaml_mapping_bounded(at_limit, 100_000, label="case.yaml")
    over = tmp_path / "over.yaml"
    over.write_text("root: " + "[" * 7 + "0" + "]" * 7 + "\n")  # depth 9
    with pytest.raises(ValidationError):
        read_yaml_mapping_bounded(over, 100_000, label="case.yaml")


def test_yaml_deep_nesting_raises_typed_error_not_recursionerror(tmp_path):
    # Far past the default depth cap: the depth guard fires a typed ValidationError
    # before any parser-driven RecursionError could escape.
    path = tmp_path / "deep.yaml"
    path.write_text("root: " + "[" * 5000 + "0" + "]" * 5000 + "\n")
    with pytest.raises(ValidationError):
        read_yaml_mapping_bounded(path, 1_000_000, label="case.yaml")


# --------------------------------------------------------------------------- #
# HTTP reviewer: decoded-byte authority, strict UTF-8, JSON containment       #
# --------------------------------------------------------------------------- #


def test_http_absent_content_length_under_limit_accepted():
    payload = json.dumps(_VALID).encode()
    resp = _json_reviewer(lambda r: httpx.Response(200, content=iter([payload]))).review(_ctx())
    assert resp.invalid_output is False


def test_http_overstated_content_length_small_body_accepted():
    # Content-Length is not consulted, so an overstated length with a small body
    # is still accepted on the streamed-byte count.
    body = json.dumps(_VALID).encode()

    def handler(req):
        return httpx.Response(
            200, content=body, headers={"content-length": str(limits.RAW_RESPONSE_BYTES * 4)}
        )

    assert _json_reviewer(handler).review(_ctx()).invalid_output is False


def test_http_understated_content_length_large_body_rejected():
    body = b"x" * (limits.RAW_RESPONSE_BYTES + 1)

    def handler(req):
        return httpx.Response(200, content=body, headers={"content-length": "5"})

    resp = _json_reviewer(handler).review(_ctx())
    assert resp.invalid_output is True
    assert resp.parsed_response.review_summary == "reviewer_output_too_large"


def test_http_gzip_decoded_bytes_authoritative():
    # Small transferred (compressed) body whose DECODED size exceeds the cap.
    decoded = json.dumps(_VALID).encode() + b" " * (limits.RAW_RESPONSE_BYTES + 100)
    compressed = gzip.compress(decoded)
    assert len(compressed) < limits.RAW_RESPONSE_BYTES  # transferred is small

    def handler(req):
        return httpx.Response(200, content=compressed, headers={"content-encoding": "gzip"})

    resp = _json_reviewer(handler).review(_ctx())
    assert resp.invalid_output is True
    assert resp.parsed_response.review_summary == "reviewer_output_too_large"


def test_http_invalid_utf8_2xx_plain_json_is_invalid():
    body = b'{"findings": []}\xff\xfe'  # invalid UTF-8 in a successful body
    resp = _json_reviewer(lambda r: httpx.Response(200, content=body)).review(_ctx())
    assert resp.invalid_output is True
    assert "valid UTF-8" in resp.parsed_response.review_summary


def test_http_invalid_utf8_2xx_openai_envelope_is_invalid():
    body = b'{"choices": [{"message": {"content": "x"}}]}\xff'
    resp = HttpReviewer(
        "http://local/v1",
        style="openai",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)),
    ).review(_ctx())
    assert resp.invalid_output is True
    assert "valid UTF-8" in resp.parsed_response.review_summary


def test_http_deeply_nested_envelope_is_contained():
    body = (b"[" * 50_000) + (b"]" * 50_000)  # valid UTF-8, within byte cap, deeply nested
    assert len(body) < limits.RAW_RESPONSE_BYTES
    resp = HttpReviewer(
        "http://local/v1",
        style="openai",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)),
    ).review(_ctx())
    assert resp.invalid_output is True  # contained as invalid, run not crashed


def test_http_deeply_nested_plain_json_is_contained():
    body = (b"[" * 50_000) + (b"]" * 50_000)
    resp = _json_reviewer(lambda r: httpx.Response(200, content=body)).review(_ctx())
    assert resp.invalid_output is True
