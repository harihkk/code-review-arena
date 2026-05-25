"""Small, deterministic helpers for paths in unified diffs."""

from __future__ import annotations


def normalize_patch_path(path: str) -> str:
    """Remove git diff prefixes while retaining repository-relative paths."""
    clean = path.strip().split("\t", 1)[0].split(" ", 1)[0]
    if clean in {"/dev/null", "dev/null"}:
        return ""
    if clean.startswith(("a/", "b/")):
        return clean[2:]
    return clean


def touched_files(patch_text: str) -> list[str]:
    """Return normalized target paths referenced by a unified diff."""
    paths: list[str] = []
    for line in patch_text.splitlines():
        if not line.startswith("+++ "):
            continue
        path = normalize_patch_path(line[4:])
        if path and path not in paths:
            paths.append(path)
    return paths
