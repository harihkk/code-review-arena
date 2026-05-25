"""Score structured reviewer findings against one seeded primary bug."""

from __future__ import annotations

from arena.core.models import (
    BenchmarkCase,
    CaseResult,
    Finding,
    ReviewerResponse,
    ScoreBreakdown,
    ScoredFinding,
)
from arena.scoring.false_positive import classify_false_positive
from arena.scoring.fix_quality import fix_quality_score
from arena.scoring.line_matcher import line_match_score, normalize_path, path_matches
from arena.scoring.semantic_matcher import concept_score
from arena.scoring.severity_matcher import severity_score


def _candidate_components(
    finding: Finding, case: BenchmarkCase
) -> tuple[float, float, float, float, str]:
    bug = case.ground_truth.primary_bug
    concept = concept_score(finding, case)
    file_score = 0.0
    line_score = 0.0
    line_match = "wrong_file"
    for expected in bug.files:
        if path_matches(finding.file, expected.path):
            file_score = 20
            score, match = line_match_score(finding, expected)
            if score > line_score:
                line_score, line_match = score, match
    severity = severity_score(finding.severity, case.severity)
    return concept, file_score, line_score, severity, line_match


def score_case(
    case: BenchmarkCase, response: ReviewerResponse, test_output: str = ""
) -> CaseResult:
    parsed = response.parsed_response
    findings = parsed.findings if parsed else []
    best_index: int | None = None
    best_components = (0.0, 0.0, 0.0, 0.0, "wrong_file")
    best_value = -1.0
    for index, finding in enumerate(findings):
        components = _candidate_components(finding, case)
        value = sum(components[:4]) + fix_quality_score(finding, case)
        if value > best_value:
            best_index, best_components, best_value = index, components, value
    concept, file_score, line_score, severity, line_match = best_components
    matched = best_index is not None and concept > 0 and file_score > 0
    fix_score = (
        fix_quality_score(findings[best_index], case) if matched and best_index is not None else 0
    )
    expected_files = {
        normalize_path(expected.path) for expected in case.ground_truth.primary_bug.files
    }
    scored: list[ScoredFinding] = []
    false_positives = 0
    for index, finding in enumerate(findings):
        true_positive = bool(matched and index == best_index)
        reason = None
        if not true_positive:
            false_positives += 1
            reason = classify_false_positive(finding, expected_files)
        scored.append(
            ScoredFinding(
                finding=finding, is_true_positive=true_positive, false_positive_reason=reason
            )
        )
    no_fp = 5 if false_positives == 0 else 0
    fp_penalty = false_positives * case.scoring.false_positive_penalty
    invalid_penalty = case.scoring.invalid_json_penalty if response.invalid_output else 0
    total = max(
        0,
        concept
        + file_score
        + line_score
        + severity
        + fix_score
        + no_fp
        - fp_penalty
        - invalid_penalty,
    )
    breakdown = ScoreBreakdown(
        concept_match=concept,
        file_match=file_score,
        line_overlap=line_score,
        severity_match=severity,
        fix_quality=fix_score,
        no_false_positives=no_fp,
        false_positive_penalty=fp_penalty,
        invalid_json_penalty=invalid_penalty,
        total=round(total, 2),
    )
    return CaseResult(
        case_id=case.id,
        title=case.title,
        category=case.category,
        severity=case.severity,
        ground_truth_summary=case.ground_truth.primary_bug.summary,
        response=response,
        scored_findings=scored,
        breakdown=breakdown,
        score=breakdown.total,
        review_quality_score=breakdown.total,
        bug_found=matched,
        correct_file=file_score == 20,
        correct_line=line_score in {8, 15},
        line_match=line_match,
        false_positive_count=false_positives,
        test_output=test_output,
    )
