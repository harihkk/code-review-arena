"""Neutral, bounded readers for benchmark pack artifacts.

These live outside ``arena/reviewers`` so the validator, execution, mutation, and
reviewer paths all read pack-controlled artifacts through the same bounded reader
and therefore cannot disagree about which bytes were accepted.
"""

from __future__ import annotations

from pathlib import Path

from arena.core import limits
from arena.core.bounded_io import read_text_bounded

REFERENCE_PATCH_LABEL = "reference.patch"


def load_reference_patch(path: Path) -> str:
    """Bounded, strict-UTF-8 read of a ``reference.patch`` artifact.

    Raises a typed ``ValidationError`` subclass for missing, unsafe-type, too-large,
    or invalid-UTF-8 input. Returns the text otherwise (which may be empty); whether
    an empty patch is acceptable is the caller's decision. Every caller receives the
    same bytes under the same limit, so no path can apply a partial patch.
    """
    return read_text_bounded(path, limits.PATCH_BYTES, label=REFERENCE_PATCH_LABEL)
