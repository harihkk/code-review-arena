from pathlib import Path

import pytest


@pytest.fixture
def benchmark_dir() -> Path:
    return Path("benchmark_sets/v1")
