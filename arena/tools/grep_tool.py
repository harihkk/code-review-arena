"""Small deterministic grep implementation for reviewer tooling."""

from pathlib import Path


def grep(root: Path, pattern: str) -> list[str]:
    matches: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(lines, start=1):
            if pattern in line:
                matches.append(f"{path.relative_to(root)}:{line_no}:{line.strip()}")
    return matches
