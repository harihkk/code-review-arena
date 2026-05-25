"""Defensive parsing for reviewer JSON output."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from arena.core.models import ReviewResult


def _parse(candidate: str) -> ReviewResult | None:
    try:
        return ReviewResult.model_validate(json.loads(candidate))
    except (json.JSONDecodeError, ValueError):
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
