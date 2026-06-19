"""Score structured reviewer findings against multi-bug ground truth.

Each ground-truth bug can be matched by at most one finding and vice versa
(maximum-weight one-to-one assignment by weighted score). Component scores are scaled
to the case's declared ``scoring.weights``, so per-case weight tuning is
actually applied. Extra findings matching the case's ``acceptable_findings``
allowlist are scored neutral; the remainder count as false positives with a
capped penalty.
"""

from __future__ import annotations

from dataclasses import dataclass

from arena.core.models import (
    BenchmarkCase,
    CaseResult,
    Finding,
    ReviewerResponse,
    ScoreBreakdown,
    ScoredFinding,
)
from arena.scoring.concept_matcher import concept_ratio, finding_text, mentions
from arena.scoring.false_positive import classify_false_positive
from arena.scoring.fix_quality import WEAK_FIX_CAP, fix_quality_ratio
from arena.scoring.line_matcher import (
    LINE_MATCH_RATIOS,
    LOCALIZED_QUALITIES,
    LineMatchQuality,
    line_match_quality,
    normalize_path,
    path_matches,
)
from arena.scoring.severity_matcher import severity_ratio


@dataclass
class _PairComponents:
    """0..1 component ratios for one finding evaluated against one bug."""

    concept: float
    file: float
    line: float
    severity: float
    fix: float
    line_quality: LineMatchQuality

    def weighted_value(self, case: BenchmarkCase) -> float:
        weights = case.scoring.weights
        return (
            self.concept * weights.concept_match
            + self.file * weights.file_match
            + self.line * weights.line_overlap
            + self.severity * weights.severity_match
            + self.fix * weights.fix_quality
        )


def _pair_components(
    finding: Finding, case: BenchmarkCase, bug_index: int
) -> _PairComponents | None:
    """Component ratios for an eligible finding/bug pair, or None when ineligible."""
    bug = case.ground_truth.bugs[bug_index]
    file_ratio = 0.0
    best_quality: LineMatchQuality = "wrong_file"
    for expected in bug.files:
        if not path_matches(finding.file, expected.path):
            continue
        file_ratio = 1.0
        quality = line_match_quality(finding, expected)
        if LINE_MATCH_RATIOS[quality] > LINE_MATCH_RATIOS[best_quality]:
            best_quality = quality
    concept = concept_ratio(finding, bug, case.category)
    if file_ratio == 0.0 or concept <= 0.0:
        return None
    return _PairComponents(
        concept=concept,
        file=file_ratio,
        line=LINE_MATCH_RATIOS[best_quality],
        severity=severity_ratio(finding.severity, case.severity),
        fix=fix_quality_ratio(finding, bug),
        line_quality=best_quality,
    )


# Sentinel cost for a forbidden (ineligible) bug/finding pair. Larger than any real
# total (weights are bounded by the per-case scoring weights, which sum to 100), so
# a min-cost assignment never chooses a forbidden pair when an unmatched slot exists.
_FORBIDDEN_COST = 1e9


def _hungarian_min_cost(cost: list[list[float]], rows: int, cols: int) -> list[int]:
    """Assignment-problem solver: assign each row a distinct column, min total cost.

    Standard O(rows^2 * cols) Hungarian (Kuhn-Munkres with potentials); requires
    rows <= cols. Returns assignment[row] = column. Deterministic for a given
    matrix (columns are scanned in ascending order, so ties resolve to the lowest
    column index).
    """
    inf = float("inf")
    u = [0.0] * (rows + 1)
    v = [0.0] * (cols + 1)
    p = [0] * (cols + 1)  # p[col] = row matched to col (1-indexed; 0 = none)
    way = [0] * (cols + 1)
    for i in range(1, rows + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (cols + 1)
        used = [False] * (cols + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = -1
            for j in range(1, cols + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(cols + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    assignment = [-1] * rows
    for j in range(1, cols + 1):
        if p[j] > 0:
            assignment[p[j] - 1] = j - 1
    return assignment


def _max_weight_matching(weights: dict[tuple[int, int], float], num_bugs: int) -> dict[int, int]:
    """Deterministic maximum-weight one-to-one matching of bugs to findings.

    Greedy assignment (take the single highest-weight pair, repeat) can be
    globally suboptimal: a finding that is the best match for two bugs hogs one
    and leaves the other unmatched even when a different pairing scores higher in
    total. This returns the exact maximum-weight matching with no approximation.

    It reduces to a square assignment problem solved by the Hungarian algorithm:
    bugs are rows; columns are the eligible findings plus one zero-cost dummy per
    bug (so a bug can stay unmatched). Eligible pairs cost their negated weight
    (minimizing cost maximizes weight); ineligible pairs are forbidden. Time is
    polynomial -- O(bugs^2 * (findings + bugs)) -- and the input is bounded by the
    MAX_BUGS_PER_CASE / MAX_FINDINGS_PER_RESPONSE schema caps, so it cannot be
    driven into a denial of service. Ties resolve to the lowest finding index.
    """
    if num_bugs == 0 or not weights:
        return {}
    finding_ids = sorted({finding for (_bug, finding) in weights})
    real_cols = len(finding_ids)
    total_cols = real_cols + num_bugs  # one dummy "unmatched" column per bug
    cost = [[0.0] * total_cols for _ in range(num_bugs)]
    for bug in range(num_bugs):
        for index in range(real_cols):
            weight = weights.get((bug, finding_ids[index]))
            cost[bug][index] = -weight if weight is not None else _FORBIDDEN_COST
        # dummy columns already 0.0: matching a bug to one means "unmatched".
    assignment = _hungarian_min_cost(cost, num_bugs, total_cols)
    result: dict[int, int] = {}
    for bug, column in enumerate(assignment):
        if 0 <= column < real_cols and (bug, finding_ids[column]) in weights:
            result[bug] = finding_ids[column]
    return result


def _assign_findings_to_bugs(
    findings: list[Finding], case: BenchmarkCase
) -> dict[int, tuple[int, _PairComponents]]:
    """Maximum-weight one-to-one assignment of findings to bugs."""
    components: dict[tuple[int, int], _PairComponents] = {}
    weights: dict[tuple[int, int], float] = {}
    for finding_index, finding in enumerate(findings):
        for bug_index in range(len(case.ground_truth.bugs)):
            pair = _pair_components(finding, case, bug_index)
            if pair is not None:
                components[(bug_index, finding_index)] = pair
                weights[(bug_index, finding_index)] = pair.weighted_value(case)
    matching = _max_weight_matching(weights, len(case.ground_truth.bugs))
    return {
        bug_index: (finding_index, components[(bug_index, finding_index)])
        for bug_index, finding_index in matching.items()
    }


def _is_acceptable(finding: Finding, case: BenchmarkCase) -> bool:
    text = finding_text(finding)
    for acceptable in case.ground_truth.acceptable_findings:
        if acceptable.path is not None and not path_matches(finding.file, acceptable.path):
            continue
        if any(mentions(text, phrase) for phrase in acceptable.concepts):
            return True
    return False


def _primary_file_signal(
    findings: list[Finding], case: BenchmarkCase
) -> tuple[bool, LineMatchQuality]:
    """File/line localization signal for the primary bug across all findings."""
    correct_file = False
    best: LineMatchQuality = "wrong_file"
    for finding in findings:
        for expected in case.ground_truth.bugs[0].files:
            if not path_matches(finding.file, expected.path):
                continue
            correct_file = True
            quality = line_match_quality(finding, expected)
            if LINE_MATCH_RATIOS[quality] > LINE_MATCH_RATIOS[best]:
                best = quality
    return correct_file, best


def score_case(
    case: BenchmarkCase, response: ReviewerResponse, test_output: str = ""
) -> CaseResult:
    parsed = response.parsed_response
    findings = parsed.findings if parsed else []
    bugs = case.ground_truth.bugs
    weights = case.scoring.weights
    assigned = _assign_findings_to_bugs(findings, case)
    finding_to_bug = {
        finding_index: bug_index for bug_index, (finding_index, _) in assigned.items()
    }

    expected_files = {normalize_path(item.path) for bug in bugs for item in bug.files}
    scored: list[ScoredFinding] = []
    false_positives = 0
    for index, finding in enumerate(findings):
        bug_index = finding_to_bug.get(index)
        if bug_index is not None:
            scored.append(
                ScoredFinding(finding=finding, is_true_positive=True, matched_bug_index=bug_index)
            )
            continue
        if _is_acceptable(finding, case):
            scored.append(
                ScoredFinding(
                    finding=finding,
                    is_true_positive=False,
                    is_neutral=True,
                    false_positive_reason="acceptable_finding",
                )
            )
            continue
        false_positives += 1
        scored.append(
            ScoredFinding(
                finding=finding,
                is_true_positive=False,
                false_positive_reason=classify_false_positive(finding, expected_files),
            )
        )

    # Case component scores are the per-bug weighted components averaged over
    # all bugs, so a case totals at most ~100 regardless of bug count.
    bug_count = len(bugs)
    concept = file_score = line_score = severity = fix_score = 0.0
    for _bug_index, (_finding_index, components) in assigned.items():
        concept += components.concept * weights.concept_match / bug_count
        file_score += components.file * weights.file_match / bug_count
        line_score += components.line * weights.line_overlap / bug_count
        severity += components.severity * weights.severity_match / bug_count
        fix_score += components.fix * weights.fix_quality / bug_count

    no_fp = weights.no_false_positives if false_positives == 0 else 0.0
    fp_penalty = min(
        false_positives * case.scoring.false_positive_penalty,
        case.scoring.false_positive_penalty_cap,
    )
    invalid_penalty = case.scoring.invalid_json_penalty if response.invalid_output else 0.0
    total = max(
        0.0,
        concept
        + file_score
        + line_score
        + severity
        + fix_score
        + no_fp
        - fp_penalty
        - invalid_penalty,
    )

    primary_matched = 0 in assigned
    if primary_matched:
        correct_file = True
        primary_quality = assigned[0][1].line_quality
    else:
        correct_file, primary_quality = _primary_file_signal(findings, case)

    breakdown = ScoreBreakdown(
        concept_match=round(concept, 2),
        file_match=round(file_score, 2),
        line_overlap=round(line_score, 2),
        severity_match=round(severity, 2),
        fix_quality=round(fix_score, 2),
        no_false_positives=round(no_fp, 2),
        false_positive_penalty=round(fp_penalty, 2),
        invalid_json_penalty=round(invalid_penalty, 2),
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
        bug_found=primary_matched,
        correct_file=correct_file,
        correct_line=primary_quality in LOCALIZED_QUALITIES,
        line_match=primary_quality,
        bugs_total=bug_count,
        bugs_matched=len(assigned),
        false_positive_count=false_positives,
        test_output=test_output,
    )


def apply_execution_fix_quality(
    case: BenchmarkCase, result: CaseResult, *, validated: bool
) -> CaseResult:
    """Override the primary bug's keyword fix score with execution evidence.

    Execution is the authoritative fix-quality signal in patch/full mode: a
    patch that applied and passed the case's required tests and validators
    earns the full fix weight; anything else caps the textual keyword score at
    the weak-fallback level so keyword stuffing cannot outrank a working fix.
    """
    primary = next((item for item in result.scored_findings if item.matched_bug_index == 0), None)
    if primary is None:
        return result
    bug = case.ground_truth.bugs[0]
    weights = case.scoring.weights
    old_ratio = fix_quality_ratio(primary.finding, bug)
    new_ratio = 1.0 if validated else min(old_ratio, WEAK_FIX_CAP)
    if new_ratio == old_ratio:
        return result
    delta = (new_ratio - old_ratio) * weights.fix_quality / max(result.bugs_total, 1)
    breakdown = result.breakdown
    components = (
        breakdown.concept_match
        + breakdown.file_match
        + breakdown.line_overlap
        + breakdown.severity_match
        + (breakdown.fix_quality + delta)
        + breakdown.no_false_positives
    )
    total = round(
        max(0.0, components - breakdown.false_positive_penalty - breakdown.invalid_json_penalty),
        2,
    )
    new_breakdown = breakdown.model_copy(
        update={"fix_quality": round(breakdown.fix_quality + delta, 2), "total": total}
    )
    return result.model_copy(
        update={"breakdown": new_breakdown, "score": total, "review_quality_score": total}
    )
