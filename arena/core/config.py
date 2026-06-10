"""Runtime configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_BENCHMARK_SET = Path("benchmark_sets/v1")
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_DB_PATH = Path("arena.db")
PROMPT_VERSION = "v1"

# Version of the JSON the dashboard consumes (audit report + verification snapshot).
# Bump on any breaking shape change; the dashboard refuses to render a mismatch.
REPORT_SCHEMA_VERSION = "1.0"


def project_root() -> Path:
    """Anchor for default paths so commands behave the same from any directory.

    ARENA_PROJECT_ROOT wins; otherwise walk up from the working directory to
    the first directory containing a benchmark_sets dir or a pyproject.toml,
    falling back to the working directory itself.
    """
    env = os.getenv("ARENA_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "benchmark_sets").is_dir() or (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def database_path() -> Path:
    value = os.getenv("ARENA_DB_PATH")
    return Path(value) if value else project_root() / DEFAULT_DB_PATH


def runs_path() -> Path:
    value = os.getenv("ARENA_RUNS_DIR")
    return Path(value) if value else project_root() / DEFAULT_RUNS_DIR


def benchmark_root() -> Path:
    """Directory that contains the named benchmark packs the server may load."""
    value = os.getenv("ARENA_BENCHMARK_ROOT")
    return Path(value) if value else project_root() / "benchmark_sets"


def resolve_benchmark_set(name: str) -> Path | None:
    """Resolve a stored benchmark-set name to a directory under benchmark_root.

    Names are identifiers, not paths: anything containing separators or parent
    references is rejected so stored run rows cannot steer the server outside
    the configured root.
    """
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    candidate = benchmark_root() / name
    return candidate if candidate.is_dir() else None


def resolve_benchmark_path(path: Path) -> Path:
    """Resolve a CLI benchmark-set path against the project root when needed."""
    if path.is_absolute() or path.exists():
        return path
    candidate = project_root() / path
    return candidate if candidate.exists() else path
