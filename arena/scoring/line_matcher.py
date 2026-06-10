"""File normalization and line-overlap quality classification."""

from pathlib import PurePosixPath
from typing import Literal

from arena.core.models import Finding, GroundTruthFile

LineMatchQuality = Literal["full", "partial", "same_file", "wrong_file"]

# Fraction of the line-overlap weight earned at each quality level.
LINE_MATCH_RATIOS: dict[LineMatchQuality, float] = {
    "full": 1.0,
    "partial": 8 / 15,
    "same_file": 3 / 15,
    "wrong_file": 0.0,
}

# Qualities that count as correct line localization.
LOCALIZED_QUALITIES: frozenset[str] = frozenset({"full", "partial"})


def normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("./")
    if normalized.startswith("a/") or normalized.startswith("b/"):
        normalized = normalized[2:]
    return PurePosixPath(normalized).as_posix()


def path_matches(candidate: str, expected: str) -> bool:
    return normalize_path(candidate) == normalize_path(expected)


def line_match_quality(finding: Finding, target: GroundTruthFile) -> LineMatchQuality:
    if not path_matches(finding.file, target.path):
        return "wrong_file"
    quality: LineMatchQuality = "same_file"
    for expected in target.line_ranges:
        overlap_start = max(finding.line_start, expected.start)
        overlap_end = min(finding.line_end, expected.end)
        if overlap_start <= overlap_end:
            if finding.line_start <= expected.start and finding.line_end >= expected.end:
                return "full"
            quality = "partial"
    return quality
