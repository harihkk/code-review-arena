"""Strict JSON decoding shared by every reviewer-output parse path.

``json.loads`` defaults are not strict enough for an adversarial reviewer: it
keeps the last of duplicate keys, accepts ``NaN``/``Infinity``/``-Infinity``, and
turns exponent overflow into a non-finite float. This decoder is the single strict
path used by exact parsing, tolerant/repair salvage, and the OpenAI outer
envelope. It rejects duplicate keys at every level, the non-standard numeric
constants, non-finite floats (including overflow), and excessive depth/node count,
and converts every parser-controlled failure into a bounded ``StrictJSONError``.

The RAW_RESPONSE_BYTES ceiling enforced before reading remains the first boundary;
these structure caps complement it, they do not replace it.
"""

from __future__ import annotations

import json
import math
from typing import Any

from arena.core import limits

# Bound for the failure message: never echo the full reviewer output back.
_REASON_LEN = 200


class StrictJSONError(ValueError):
    """A reviewer payload failed strict JSON decoding (bounded, no full content)."""


def _reject_constant(name: str) -> float:
    # parse_constant fires for the bare NaN/Infinity/-Infinity tokens.
    raise StrictJSONError(f"non-standard JSON constant: {name}")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            raise StrictJSONError("duplicate key in a JSON object")
        seen.add(key)
    return dict(pairs)


def _validate_structure(root: Any) -> None:
    """Iteratively bound depth, node count, and float finiteness (no recursion)."""
    nodes = 0
    stack: list[tuple[Any, int]] = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > limits.JSON_MAX_DEPTH:
            raise StrictJSONError("JSON nested too deeply")
        nodes += 1
        if nodes > limits.JSON_MAX_NODES:
            raise StrictJSONError("JSON has too many nodes")
        if isinstance(node, float) and not math.isfinite(node):
            # Exponent overflow (e.g. 1e400) materializes here even though it is
            # not one of the named constants parse_constant rejects.
            raise StrictJSONError("non-finite JSON number")
        if isinstance(node, dict):
            for value in node.values():
                stack.append((value, depth + 1))
        elif isinstance(node, list):
            for value in node:
                stack.append((value, depth + 1))


def strict_loads(text: str) -> Any:
    """Decode one JSON document strictly, or raise a bounded ``StrictJSONError``.

    Never catches BaseException/KeyboardInterrupt/SystemExit, and never includes
    the full input in the error.
    """
    try:
        data = json.loads(
            text,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except StrictJSONError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise StrictJSONError(f"invalid JSON ({type(exc).__name__})") from exc
    _validate_structure(data)
    return data
