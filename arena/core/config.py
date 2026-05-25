"""Runtime configuration helpers."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_BENCHMARK_SET = Path("benchmark_sets/v1")
DEFAULT_RUNS_DIR = Path("runs")
DEFAULT_DB_PATH = Path("arena.db")
PROMPT_VERSION = "v1"


def database_path() -> Path:
    return Path(os.getenv("ARENA_DB_PATH", str(DEFAULT_DB_PATH)))


def runs_path() -> Path:
    return Path(os.getenv("ARENA_RUNS_DIR", str(DEFAULT_RUNS_DIR)))
