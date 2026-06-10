"""Invoke an external command to produce structured review JSON."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from arena.core.models import CaseContext, ReviewerResponse, ReviewResult
from arena.reviewers.base import BaseReviewer
from arena.reviewers.response_parser import parse_review_response


def serialize_reviewer_case(
    context: CaseContext, *, reveal_metadata: bool = False
) -> dict[str, object]:
    """Blind reviewer payload: code and diff only, never ground truth.

    Case title/description/category/severity frequently paraphrase the seeded
    bug, so they are excluded unless reveal_metadata is set (debugging only;
    scored runs should stay blind).
    """
    payload: dict[str, object] = {
        "case_id": context.case.id,
        "stack": context.case.stack,
        "pr_diff": context.diff,
        "relevant_files": context.relevant_files,
    }
    if context.context_truncated:
        payload["context_truncated"] = True
    if reveal_metadata:
        payload["title"] = context.case.title
        payload["category"] = context.case.category
        payload["severity"] = context.case.severity
        payload["description"] = context.case.description
    if context.test_output:
        payload["test_output"] = context.test_output
    if context.static_analysis_output:
        payload["static_analysis_output"] = context.static_analysis_output
    return payload


def expand_command_template(
    template: str,
    *,
    case_json: Path,
    diff_file: Path,
    case_id: str,
    workspace: Path,
) -> list[str]:
    expanded = (
        template.replace("{case_json}", str(case_json))
        .replace("{diff_file}", str(diff_file))
        .replace("{case_id}", case_id)
        .replace("{workspace}", str(workspace))
    )
    return shlex.split(expanded)


class CustomCommandReviewer(BaseReviewer):
    name = "custom-command"
    model = "custom"

    def __init__(
        self,
        command_template: str,
        timeout_seconds: int = 120,
        reveal_metadata: bool = False,
    ) -> None:
        self.command_template = command_template
        self.timeout_seconds = timeout_seconds
        self.reveal_metadata = reveal_metadata

    def review(self, context: CaseContext) -> ReviewerResponse:
        started = time.perf_counter()
        temp_dir = Path(tempfile.mkdtemp(prefix="arena-custom-command-"))
        try:
            workspace = temp_dir / "workspace"
            workspace.mkdir()
            case_json = temp_dir / "case.json"
            diff_file = temp_dir / "pr.diff"
            case_json.write_text(
                json.dumps(
                    serialize_reviewer_case(context, reveal_metadata=self.reveal_metadata),
                    indent=2,
                ),
                encoding="utf-8",
            )
            diff_file.write_text(context.diff, encoding="utf-8")
            for relative_path, contents in context.relevant_files.items():
                target = workspace / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents, encoding="utf-8")
            args = expand_command_template(
                self.command_template,
                case_json=case_json,
                diff_file=diff_file,
                case_id=context.case.id,
                workspace=workspace,
            )
            completed = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
                check=False,
            )
            raw = completed.stdout.strip() or completed.stderr.strip()
            error_notes: list[str] = []
            if completed.returncode != 0:
                error_notes.append(f"command exited with code {completed.returncode}")
            if completed.stderr.strip():
                error_notes.append(completed.stderr.strip()[-500:])
            parsed, attempts = parse_review_response(raw if raw else "{}")
            invalid = parsed is None or completed.returncode != 0 or not raw
            if invalid and error_notes:
                summary = "; ".join(error_notes)
                parsed = ReviewResult(
                    findings=[],
                    overall_risk="none",
                    review_summary=f"Custom command failed: {summary}",
                )
            return ReviewerResponse(
                raw_response=raw or json.dumps({"error": error_notes}),
                parsed_response=parsed,
                invalid_output=invalid,
                parse_attempts=attempts,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except subprocess.TimeoutExpired:
            raw = json.dumps({"error": f"command timed out after {self.timeout_seconds}s"})
            parsed, attempts = parse_review_response(raw)
            return ReviewerResponse(
                raw_response=raw,
                parsed_response=parsed,
                invalid_output=True,
                parse_attempts=attempts,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
