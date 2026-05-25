#!/usr/bin/env python3
"""Example external reviewer for custom-command benchmarking."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "tests/fixtures/fake_reviewers/valid_reviewer.py"
    sys.argv[0] = str(target)
    runpy.run_path(str(target), run_name="__main__")
