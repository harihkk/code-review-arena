"""JSON report persistence."""

import json
from pathlib import Path

from arena.core.models import RunResult


def write_json_report(run: RunResult, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(run.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def read_json_report(path: Path) -> RunResult:
    return RunResult.model_validate_json(path.read_text(encoding="utf-8"))
