"""File normalization and line-overlap scoring."""

from pathlib import PurePosixPath

from arena.core.models import Finding, GroundTruthFile


def normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("./")
    if normalized.startswith("a/") or normalized.startswith("b/"):
        normalized = normalized[2:]
    return PurePosixPath(normalized).as_posix()


def path_matches(candidate: str, expected: str) -> bool:
    return normalize_path(candidate) == normalize_path(expected)


def line_match_score(finding: Finding, target: GroundTruthFile) -> tuple[float, str]:
    if not path_matches(finding.file, target.path):
        return 0, "wrong_file"
    result = "none"
    for expected in target.line_ranges:
        overlap_start = max(finding.line_start, expected.start)
        overlap_end = min(finding.line_end, expected.end)
        if overlap_start <= overlap_end:
            if finding.line_start <= expected.start and finding.line_end >= expected.end:
                return 15, "full"
            result = "partial"
    if result == "partial":
        return 8, result
    return 3, "same_file"
