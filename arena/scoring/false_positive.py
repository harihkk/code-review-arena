"""Classification helpers for unmatched comments."""

from arena.core.models import Finding


def classify_false_positive(finding: Finding, expected_files: set[str]) -> str:
    summary = f"{finding.title} {finding.summary}".casefold()
    if "style" in summary or "rename" in summary or "format" in summary:
        return "style-only"
    if finding.file not in expected_files:
        return "wrong-file"
    if "may" in summary or "could" in summary:
        return "unsupported-speculation"
    return "non-bug"
