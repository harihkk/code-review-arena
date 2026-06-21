"""Invoke an external command to produce structured review JSON."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
import time
from pathlib import Path

from arena.core import limits
from arena.core.errors import ExecutionError
from arena.core.models import CaseContext, ReviewerResponse, ReviewResult
from arena.execution.process import run_supervised
from arena.reviewers.base import BaseReviewer
from arena.reviewers.response_parser import naive_repair, parse_review_response


def serialize_reviewer_case(
    context: CaseContext,
    *,
    reveal_metadata: bool = False,
    reveal_test_output: bool = False,
) -> dict[str, object]:
    """Blind reviewer payload: case id, stack, diff, and relevant files only.

    Nothing derived from ground truth is included by default. Case
    title/description/category/severity paraphrase the seeded bug, and the
    pre-patch test/static-analysis output reveals the failing assertion's
    expected values (which localize the bug and disclose correct behavior), so
    both are gated behind explicit opt-in flags. A scored blind run leaves them
    off; reveal_metadata is for debugging and reveal_test_output is an openly
    test-assisted mode that the run records and reports separately.
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
    if reveal_test_output:
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


_SECRET_VALUE = re.compile(r"(?i)(\b\w*(?:key|token|secret|password)\w*\s*[=:]\s*)(\S+)")
_BEARER_VALUE = re.compile(r"(?i)\b(bearer\s+)(\S+)")


def redact_secrets(text: str) -> str:
    """Mask credential-looking values so command templates can be persisted."""
    return _BEARER_VALUE.sub(r"\1***", _SECRET_VALUE.sub(r"\1***", text))


class CustomCommandReviewer(BaseReviewer):
    name = "custom-command"
    model = "custom"

    def __init__(
        self,
        command_template: str,
        timeout_seconds: int = 120,
        reveal_metadata: bool = False,
        enable_repair: bool = False,
        reveal_test_output: bool = False,
    ) -> None:
        self.command_template = command_template
        self.timeout_seconds = timeout_seconds
        self.reveal_metadata = reveal_metadata
        self.enable_repair = enable_repair
        self.reveal_test_output = reveal_test_output

    def safe_config(self) -> dict[str, object]:
        return {
            "command_template": redact_secrets(self.command_template),
            "timeout_seconds": self.timeout_seconds,
            "reveal_metadata": self.reveal_metadata,
            "enable_repair": self.enable_repair,
            "reveal_test_output": self.reveal_test_output,
        }

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
                    serialize_reviewer_case(
                        context,
                        reveal_metadata=self.reveal_metadata,
                        reveal_test_output=self.reveal_test_output,
                    ),
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
            # Through the supervisor: process-tree cleanup, a byte-bounded output
            # cap, and the Windows-fail-closed boundary, not a bare subprocess.run.
            try:
                completed = run_supervised(
                    args,
                    # Inherit the caller's working directory (as the old
                    # subprocess.run did) so a relative wrapper path still
                    # resolves; the case files in args are absolute paths.
                    cwd=Path.cwd(),
                    env=dict(os.environ),
                    timeout=self.timeout_seconds,
                    # Share the centralized reviewer-output byte cap with the HTTP reviewer.
                    output_limit=limits.RAW_RESPONSE_BYTES,
                )
            except ExecutionError as exc:
                raw = json.dumps({"error": str(exc)})
                parsed, attempts = parse_review_response(raw)
                return ReviewerResponse(
                    raw_response=raw,
                    parsed_response=parsed,
                    invalid_output=True,
                    parse_attempts=attempts,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            if completed.timed_out:
                raw = json.dumps({"error": f"command timed out after {self.timeout_seconds}s"})
                parsed, attempts = parse_review_response(raw)
                return ReviewerResponse(
                    raw_response=raw,
                    parsed_response=parsed,
                    invalid_output=True,
                    parse_attempts=attempts,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            if completed.output_limit_exceeded:
                # The child flooded past the output cap and was reaped, so the captured
                # stdout/stderr are truncated. A valid JSON prefix followed by a flood
                # must NOT pass: report a stable too-large error and never parse the
                # truncated output as ordinary malformed JSON.
                raw = json.dumps({"error": "reviewer_output_too_large"})
                return ReviewerResponse(
                    raw_response=raw,
                    parsed_response=ReviewResult(
                        findings=[],
                        overall_risk="none",
                        review_summary="reviewer_output_too_large",
                    ),
                    invalid_output=True,
                    parse_attempts=1,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            raw = completed.stdout.strip() or completed.stderr.strip()
            error_notes: list[str] = []
            if completed.returncode != 0:
                error_notes.append(f"command exited with code {completed.returncode}")
            if completed.stderr.strip():
                error_notes.append(completed.stderr.strip()[-500:])
            parsed, attempts = parse_review_response(
                raw if raw else "{}",
                repair=naive_repair if self.enable_repair else None,
            )
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
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
