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


def database_path() -> Path:
    return Path(os.getenv("ARENA_DB_PATH", str(DEFAULT_DB_PATH)))


def runs_path() -> Path:
    return Path(os.getenv("ARENA_RUNS_DIR", str(DEFAULT_RUNS_DIR)))


def benchmark_root() -> Path:
    """Directory that contains the named benchmark packs the server may load."""
    return Path(os.getenv("ARENA_BENCHMARK_ROOT", "benchmark_sets"))


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
