"""Defensive parsing for reviewer JSON output."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from pydantic import ValidationError as PydanticValidationError

from arena.core.models import Finding, ReviewResult


def _parse(candidate: str) -> ReviewResult | None:
    # RecursionError guards against deeply nested (but within-byte-limit) JSON; a
    # parse/validation failure means "not a valid review", never a crashed run.
    try:
        return ReviewResult.model_validate(json.loads(candidate))
    except (json.JSONDecodeError, ValueError, RecursionError):
        return None


def tolerant_candidate(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        text = text[first : last + 1]
    return re.sub(r",(\s*[}\]])", r"\1", text)


def naive_repair(raw: str) -> str:
    """Deterministic salvage for almost-valid reviewer JSON; never calls a model.

    Wraps a bare findings list into the expected envelope, fills missing
    top-level fields with neutral defaults, and drops individual findings that
    fail validation rather than rejecting the whole response. Used only when a
    reviewer opts in (--enable-repair); the attempt is visible as
    parse_attempts=3 on the response.
    """
    data = None
    for candidate in (raw, tolerant_candidate(raw)):
        try:
            data = json.loads(candidate)
            break
        except (json.JSONDecodeError, RecursionError):
            continue
    if data is None:
        return raw
    if isinstance(data, list):
        data = {"findings": data}
    if not isinstance(data, dict):
        return raw
    data.setdefault("overall_risk", "medium")
    data.setdefault("review_summary", "")
    findings = data.get("findings")
    kept: list[object] = []
    if isinstance(findings, list):
        for item in findings:
            try:
                Finding.model_validate(item)
            except PydanticValidationError:
                continue
            kept.append(item)
    data["findings"] = kept
    return json.dumps(data)


def parse_review_response(
    raw: str, repair: Callable[[str], str] | None = None
) -> tuple[ReviewResult | None, int]:
    parsed = _parse(raw)
    if parsed is not None:
        return parsed, 1
    parsed = _parse(tolerant_candidate(raw))
    if parsed is not None:
        return parsed, 2
    if repair is not None:
        parsed = _parse(repair(raw))
        if parsed is not None:
            return parsed, 3
    return None, 3 if repair is not None else 2
