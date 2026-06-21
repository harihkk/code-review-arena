"""A generic adversarial baseline: localize the bug, then fail to repair it.

``keyword_gamer`` proves the detection-versus-validation gap on audit_v1, but it
needs hand-maintained per-case data. This reviewer needs none: it reads the
shipped ``reference.patch`` only to learn *which file* the bug lives in (so its
finding localizes like a confident review), then proposes a superficial change
that applies cleanly but does not fix anything. Detection looks strong; the
tests still fail, so validation is zero. Every pack with a reference patch gets
an adversarial baseline for free, which is the whole point of the harness:
pointing at a defect is not repairing it.
"""

from __future__ import annotations

import difflib
import json
import time

from arena.benchmark.artifacts import load_reference_patch
from arena.core.models import CaseContext, Finding, ReviewerResponse, ReviewResult
from arena.patching.patch_parser import touched_files
from arena.reviewers.base import BaseReviewer
from arena.reviewers.reference_patch import REFERENCE_PATCH_FILENAME
from arena.reviewers.response_parser import parse_review_response


class ShallowPatchReviewer(BaseReviewer):
    name = "shallow-patch"
    model = None

    def _target_file(self, context: CaseContext) -> str | None:
        """The file the bug lives in, learned from the reference patch."""
        if context.case_dir is not None:
            reference = context.case_dir / REFERENCE_PATCH_FILENAME
            if reference.is_file():
                touched = touched_files(load_reference_patch(reference))
                if touched:
                    return touched[0]
        return next(iter(context.relevant_files), None)

    @staticmethod
    def _shallow_patch(path: str, original: str) -> str | None:
        """A no-op comment insertion: a clean-applying diff that changes nothing."""
        if not original:
            return None
        if path.endswith((".ts", ".tsx", ".js", ".jsx", ".java")):
            comment = "// hardened during review\n"
        elif path.endswith(".sql"):
            comment = "-- hardened during review\n"
        else:
            comment = "# hardened during review\n"
        modified = comment + original
        return "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )

    def review(self, context: CaseContext) -> ReviewerResponse:
        started = time.perf_counter()
        path = self._target_file(context)
        original = context.relevant_files.get(path, "") if path else ""
        patch = self._shallow_patch(path, original) if path else None
        finding = Finding(
            title="Risky change in the modified code path",
            summary=(
                f"The pull request changes behavior in {path or 'the affected module'}; "
                "this path looks defective and was hardened."
            ),
            category=context.case.category,
            severity=context.case.severity,
            file=path or "unknown",
            line_start=1,
            line_end=1,
            evidence="The diff alters the behavior of this file.",
            suggested_fix="Harden the changed code path.",
            suggested_patch=patch,
            patch_confidence=0.8 if patch else None,
            confidence=0.85,
        )
        result = ReviewResult(
            findings=[finding],
            overall_risk=context.case.severity,
            review_summary=(
                f"Shallow review for {context.case.id}: the defect is localized but the "
                "proposed change does not repair it."
            ),
            proposed_patch=patch,
        )
        raw = json.dumps(result.model_dump())
        parsed, attempts = parse_review_response(raw)
        return ReviewerResponse(
            raw_response=raw,
            parsed_response=parsed,
            parse_attempts=attempts,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
