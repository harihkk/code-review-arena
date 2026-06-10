#!/usr/bin/env python3
"""Emit a bare findings list (missing envelope) to exercise the repair path."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    case = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
    primary_file = next(iter(case["relevant_files"]))
    findings = [
        {
            "title": "Detected issue",
            "summary": f"Reviewed {case['case_id']} in {primary_file}.",
            "category": "correctness",
            "severity": "medium",
            "file": primary_file,
            "line_start": 1,
            "line_end": 2,
            "evidence": "Synthetic reviewer output for tests.",
            "suggested_fix": "Apply the appropriate guard.",
            "confidence": 0.5,
        },
        {"title": "broken finding missing required fields"},
    ]
    print(json.dumps(findings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
