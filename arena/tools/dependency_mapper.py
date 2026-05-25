"""Simple dependency mapping entrypoint."""

from pathlib import Path

from arena.tools.ast_inspector import inspect_imports


def map_python_dependencies(root: Path) -> dict[str, list[str]]:
    return {path.relative_to(root).as_posix(): inspect_imports(path) for path in root.rglob("*.py")}
