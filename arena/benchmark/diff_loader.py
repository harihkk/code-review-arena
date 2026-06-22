"""Unified diff loading and changed-line extraction."""

from __future__ import annotations

import re
from pathlib import Path

from arena.core import limits
from arena.core.bounded_io import read_text_bounded
from arena.core.errors import ValidationError

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def load_diff(path: Path) -> str:
    if not path.is_file():
        raise ValidationError(f"Missing pull request diff: {path}")
    return read_text_bounded(path, limits.DIFF_BYTES, label="pull request diff")


def parse_added_lines(diff: str) -> dict[str, set[int]]:
    """Return after-file line numbers for additions in a unified diff."""
    added: dict[str, set[int]] = {}
    current_file: str | None = None
    after_line: int | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].split("\t", 1)[0]
            current_file = target[2:] if target.startswith("b/") else target
            if current_file != "/dev/null":
                added.setdefault(current_file, set())
            continue
        match = HUNK_RE.match(line)
        if match:
            after_line = int(match.group(1))
            continue
        if current_file is None or after_line is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added[current_file].add(after_line)
            after_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue
        elif line.startswith("\\"):
            continue
        else:
            after_line += 1
    return added
