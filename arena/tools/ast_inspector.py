"""Lightweight Python import inspection for tool-assisted context."""

from __future__ import annotations

import ast
from pathlib import Path


def inspect_imports(path: Path) -> list[str]:
    if path.suffix != ".py":
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return sorted(set(imports))
