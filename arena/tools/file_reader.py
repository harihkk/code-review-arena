"""Constrained source reader for a materialized case."""

from pathlib import Path


def read_file(root: Path, relative_path: str) -> str:
    candidate = (root / relative_path).resolve()
    if root.resolve() not in candidate.parents and candidate != root.resolve():
        raise ValueError("file path escapes materialized repository")
    return candidate.read_text(encoding="utf-8", errors="replace")
