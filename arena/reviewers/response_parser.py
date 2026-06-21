"""Reviewer-output parsing: exact by default, explicit development-only salvage.

Exact parsing is the comparable contract: the raw response must be exactly one
strict JSON object that validates as ``ReviewResult`` (with every finding path
admitted to a canonical pack-relative path). No Markdown-fence stripping, no
brace extraction, no trailing-comma removal, no bare-list wrapping, no field
insertion, no finding dropping. Anything else is ``invalid`` -- a legitimate
reviewer-contract failure that still scores (with the invalid-output penalty).

Salvage (tolerant transforms, then deterministic repair) runs only when the
caller opts in via ``enable_repair``. It is development-only and makes a run
non-comparable; every transformation and every dropped finding is recorded.
Salvage never calls a model and never relaxes strict JSON decoding (duplicate
keys and non-finite numbers stay rejected). Both reviewer transports use this one
parser, the same status semantics, and the same known-path admission context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from arena.core import limits
from arena.core.models import CaseContext, Finding, ParseStatus, ReviewerResponse, ReviewResult
from arena.patching.patch_parser import referenced_paths
from arena.reviewers.strict_json import StrictJSONError, strict_loads
from arena.security.paths import admit_reviewer_path

_REASON_LEN = limits.PARSE_ERROR_SUMMARY_LEN


@dataclass
class ParseOutcome:
    """The structured result of parsing one reviewer response."""

    result: ReviewResult | None
    status: ParseStatus
    attempt_count: int
    actions: list[str] = field(default_factory=list)
    # None means "no valid findings list was established" (invalid responses).
    input_finding_count: int | None = None
    retained_finding_count: int | None = None
    dropped_finding_count: int = 0
    failure_reason: str | None = None


def _short(exc: Exception) -> str:
    """A bounded failure reason that never echoes the reviewer's input values."""
    if isinstance(exc, PydanticValidationError):
        parts = [".".join(str(p) for p in e["loc"]) + ": " + e["type"] for e in exc.errors()[:5]]
        return "; ".join(parts)[:_REASON_LEN]
    return str(exc)[:_REASON_LEN]


def _invalid(attempt: int, reason: str) -> ParseOutcome:
    return ParseOutcome(
        result=None, status="invalid", attempt_count=attempt, failure_reason=reason[:_REASON_LEN]
    )


def _strip_trailing_commas(text: str) -> str:
    """Remove only structural trailing commas, never bytes inside a JSON string.

    A deterministic scanner tracking string state (with escaped quotes/backslashes):
    a comma is dropped only when it is outside a string and the next non-whitespace
    character is ``}`` or ``]``.
    """
    out: list[str] = []
    in_string = False
    escaped = False
    length = len(text)
    for index, char in enumerate(text):
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            out.append(char)
            continue
        if char == ",":
            look = index + 1
            while look < length and text[look] in " \t\r\n":
                look += 1
            if look < length and text[look] in "}]":
                continue  # structural trailing comma
        out.append(char)
    return "".join(out)


def _tolerant_transform(raw: str) -> tuple[str, list[str]]:
    """Apply only the documented tolerant transforms, recording which ones changed text."""
    text = raw.strip()
    actions: list[str] = []
    if text.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", text)
        stripped = re.sub(r"\s*```$", "", stripped)
        if stripped != text:
            actions.append("strip_markdown_fence")
            text = stripped
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first and (first > 0 or last < len(text) - 1):
        text = text[first : last + 1]
        actions.append("extract_json_object")
    without_commas = _strip_trailing_commas(text)
    if without_commas != text:
        actions.append("remove_trailing_commas")
        text = without_commas
    return text, actions


def _admit_paths_strict(data: dict[str, Any], known_paths: frozenset[str] | None) -> dict[str, Any]:
    """Admit every finding path; raise if any is inadmissible (exact/tolerant)."""
    findings = data.get("findings")
    if not isinstance(findings, list):
        return data
    admitted = [
        {**item, "file": admit_reviewer_path(item["file"], known_paths)}
        if isinstance(item, dict) and "file" in item
        else item
        for item in findings
    ]
    return {**data, "findings": admitted}


def _repair_findings(
    data: dict[str, Any], known_paths: frozenset[str] | None
) -> tuple[dict[str, Any], int, list[str]]:
    """Drop individually invalid findings (bad path or schema); record what was dropped."""
    findings = data.get("findings")
    assert isinstance(findings, list)  # guaranteed by the caller's list check
    kept: list[Any] = []
    dropped_locations: list[str] = []
    for index, item in enumerate(findings):
        try:
            if isinstance(item, dict) and "file" in item:
                item = {**item, "file": admit_reviewer_path(item["file"], known_paths)}
            Finding.model_validate(item)
            kept.append(item)
        except (ValueError, PydanticValidationError) as exc:
            dropped_locations.append(f"findings[{index}]: {_short(exc)}")
    return {**data, "findings": kept}, len(findings) - len(kept), dropped_locations


def _try_exact(raw: str, known_paths: frozenset[str] | None) -> ParseOutcome:
    try:
        data = strict_loads(raw)
    except StrictJSONError as exc:
        return _invalid(1, str(exc))
    if not isinstance(data, dict):
        return _invalid(1, "top-level JSON value is not an object")
    try:
        result = ReviewResult.model_validate(_admit_paths_strict(data, known_paths))
    except (ValueError, PydanticValidationError) as exc:
        return _invalid(1, _short(exc))
    count = len(result.findings)
    return ParseOutcome(result, "exact", 1, [], count, count, 0, None)


def _try_tolerant(raw: str, known_paths: frozenset[str] | None) -> ParseOutcome | None:
    transformed, actions = _tolerant_transform(raw)
    if not actions:
        return None  # nothing tolerant to do; exact already failed
    try:
        data = strict_loads(transformed)
        if not isinstance(data, dict):
            return None
        result = ReviewResult.model_validate(_admit_paths_strict(data, known_paths))
    except (StrictJSONError, ValueError, PydanticValidationError):
        return None  # tolerant must not drop findings; fall through to repair
    count = len(result.findings)
    return ParseOutcome(result, "tolerant", 2, actions, count, count, 0, None)


def _try_repair(raw: str, known_paths: frozenset[str] | None) -> ParseOutcome:
    # Decode the raw text first: a bare findings list is already valid JSON and must
    # not be mangled by the brace-extraction transform. Only fall back to the
    # tolerant transforms when the raw text does not decode.
    actions: list[str] = []
    try:
        data = strict_loads(raw)
    except StrictJSONError:
        transformed, transform_actions = _tolerant_transform(raw)
        actions.extend(transform_actions)
        try:
            data = strict_loads(transformed)
        except StrictJSONError as exc:
            return _invalid(3, str(exc))
    if isinstance(data, list):
        data = {"findings": data}
        actions.append("wrap_findings_list")
    if not isinstance(data, dict):
        return _invalid(3, "top-level JSON value is not an object")
    # Never invent a findings list: a missing, null, or non-list findings container
    # is invalid, not "no findings". Only a genuine list is repaired.
    findings = data.get("findings")
    if not isinstance(findings, list):
        return _invalid(3, "findings must be a JSON array")
    data = dict(data)
    if "overall_risk" not in data:
        data["overall_risk"] = "medium"
        actions.append("default_overall_risk")
    if "review_summary" not in data:
        data["review_summary"] = ""
        actions.append("default_review_summary")
    input_count = len(findings)
    data, dropped, locations = _repair_findings(data, known_paths)
    if dropped:
        actions.append("drop_invalid_findings")
    try:
        result = ReviewResult.model_validate(data)
    except (ValueError, PydanticValidationError) as exc:
        return _invalid(3, _short(exc))
    return ParseOutcome(
        result=result,
        status="repaired",
        attempt_count=3,
        actions=actions,
        input_finding_count=input_count,
        retained_finding_count=len(result.findings),
        dropped_finding_count=dropped,
        failure_reason="; ".join(locations)[:_REASON_LEN] or None,
    )


def parse_reviewer_output(
    raw: str, *, enable_repair: bool = False, known_paths: frozenset[str] | None = None
) -> ParseOutcome:
    """Parse a raw reviewer response into a structured outcome.

    Default (``enable_repair=False``): exact attempt only -- success is ``exact``,
    anything else is ``invalid``. With salvage enabled: exact, then tolerant
    transforms, then deterministic repair, recording the status and actions.
    ``known_paths`` (reviewer-visible repository paths) disambiguates Git ``a/``/``b/``
    presentation prefixes from real top-level directories; without it the prefix is
    never stripped.
    """
    exact = _try_exact(raw, known_paths)
    if exact.status == "exact" or not enable_repair:
        return exact
    tolerant = _try_tolerant(raw, known_paths)
    if tolerant is not None:
        return tolerant
    return _try_repair(raw, known_paths)


def known_paths_from_context(context: CaseContext) -> frozenset[str]:
    """The reviewer-visible repository paths used to admit Git-prefixed finding paths.

    Built only from surfaces the reviewer can see -- relevant-file keys and the
    diff's referenced paths (via the shared unified-diff helper) -- never from
    ground truth. This internal set is not sent to the reviewer.
    """
    paths = set(context.relevant_files)
    paths.update(referenced_paths(context.diff))
    return frozenset(paths)


def response_from_outcome(
    outcome: ParseOutcome, *, raw: str, latency_ms: int = 0, **extra: Any
) -> ReviewerResponse:
    """Build a ReviewerResponse from a parse outcome, preserving the raw output."""
    return ReviewerResponse(
        raw_response=raw,
        parsed_response=outcome.result,
        invalid_output=outcome.status == "invalid",
        parse_attempts=outcome.attempt_count,
        parse_status=outcome.status,
        parse_actions=list(outcome.actions),
        input_finding_count=outcome.input_finding_count,
        retained_finding_count=outcome.retained_finding_count,
        dropped_finding_count=outcome.dropped_finding_count,
        parse_error_summary=outcome.failure_reason,
        latency_ms=latency_ms,
        **extra,
    )
