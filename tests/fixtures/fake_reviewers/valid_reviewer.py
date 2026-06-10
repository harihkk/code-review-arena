#!/usr/bin/env python3
"""Emit a valid ReviewResult JSON for custom-command reviewer tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    case_path = Path(sys.argv[-1])
    case = json.loads(case_path.read_text(encoding="utf-8"))
    primary_file = next(iter(case["relevant_files"]))
    # The payload is blind: category/severity are the reviewer's own judgment.
    payload = {
        "findings": [
            {
                "title": "Detected issue",
                "summary": f"Reviewed {case['case_id']} in {primary_file}.",
                "category": case.get("category", "correctness"),
                "severity": case.get("severity", "medium"),
                "file": primary_file,
                "line_start": 1,
                "line_end": 2,
                "evidence": "Synthetic reviewer output for tests.",
                "suggested_fix": "Apply the appropriate guard.",
                "suggested_patch": None,
                "confidence": 0.5,
            }
        ],
        "overall_risk": case.get("severity", "medium"),
        "review_summary": f"Fixture review for {case['case_id']}.",
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
