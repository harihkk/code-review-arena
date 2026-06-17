"""Pydantic models shared across benchmark, reviewers, reports and API."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

Severity = Literal["critical", "high", "medium", "low"]
Risk = Literal["critical", "high", "medium", "low", "none"]
# A run's trust level. Only `complete` v2 runs are leaderboard-eligible; the rest
# are preserved and inspectable but excluded from normal comparisons.
RunStatus = Literal["complete", "partial", "invalid", "failed", "cancelled", "legacy"]
ExecutionBackend = Literal["docker", "trusted-local", "none"]
# Bumped when the run JSON shape changes in a way that breaks comparability.
RUN_SCHEMA_VERSION = 2


class LineRange(BaseModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @field_validator("end")
    @classmethod
    def end_not_before_start(cls, value: int, info: Any) -> int:
        start = info.data.get("start")
        if start is not None and value < start:
            raise ValueError("line range end cannot precede start")
        return value


class GroundTruthFile(BaseModel):
    path: str
    line_ranges: list[LineRange]


class GroundTruthBug(BaseModel):
    # Stable identifier used to attribute repairs to specific bugs. Auto-assigned
    # as bug-1, bug-2, ... by GroundTruth when a case does not declare one.
    id: str = ""
    summary: str
    files: list[GroundTruthFile]
    concepts: list[str]
    must_mention: list[str] = Field(default_factory=list)
    acceptable_fix_keywords: list[str] = Field(default_factory=list)


# Back-compat alias: cases authored against the single-bug model import PrimaryBug.
PrimaryBug = GroundTruthBug


class AcceptableFinding(BaseModel):
    """A known-good extra finding that is scored neutral, not as a false positive."""

    path: str | None = None
    concepts: list[str] = Field(min_length=1)


class GroundTruth(BaseModel):
    bugs: list[GroundTruthBug] = Field(min_length=1)
    acceptable_findings: list[AcceptableFinding] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_primary_bug(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "primary_bug" not in value:
            return value
        converted = dict(value)
        legacy = converted.pop("primary_bug")
        bugs = converted.get("bugs")
        if not bugs:
            converted["bugs"] = [legacy]
        elif bugs[0] != legacy:
            raise ValueError("primary_bug and bugs[0] disagree; declare the bug once in bugs")
        return converted

    @model_validator(mode="after")
    def _assign_bug_ids(self) -> GroundTruth:
        for index, bug in enumerate(self.bugs):
            if not bug.id:
                bug.id = f"bug-{index + 1}"
        return self

    # Serialized for dashboards and tooling built on the single-bug shape.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def primary_bug(self) -> GroundTruthBug:
        return self.bugs[0]


class CaseInput(BaseModel):
    diff: str = "pr.diff"
    before_dir: str = "before"
    after_dir: str = "after"
    tests_dir: str | None = "tests"


class ScoreWeights(BaseModel):
    concept_match: float = 35
    file_match: float = 20
    line_overlap: float = 15
    severity_match: float = 10
    fix_quality: float = 15
    no_false_positives: float = 5

    def total(self) -> float:
        return float(sum(self.model_dump().values()))


class ScoringConfig(BaseModel):
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    false_positive_penalty: float = 5
    false_positive_penalty_cap: float = Field(default=15, ge=0)
    invalid_json_penalty: float = 20


class ExecutionConfig(BaseModel):
    run_tests: bool = False
    # One command string, one argv list, or a list of argv lists run in order.
    test_command: str | list[str] | list[list[str]] | None = None
    timeout_seconds: int = Field(default=30, ge=1)
    docker_image: str | None = None
    run_static_analysis: bool = False
    static_analysis_command: str | None = None


class ValidationConfig(BaseModel):
    patch_required: bool = False
    tests_required: bool = False
    structural_validators: list[str] = Field(default_factory=list)
    max_false_positives: int = Field(default=0, ge=0)
    protected_paths: list[str] = Field(default_factory=list)
    # Detection completeness required for a deterministic pass. Defaults to
    # all_bugs: for single-bug cases this is identical to at_least_one, and for
    # multi-bug cases it correctly requires every seeded bug to be found.
    detection_requirement: Literal["all_bugs", "at_least_one"] = "all_bugs"


class MetricsConfig(BaseModel):
    beta: float = Field(default=1.0, gt=0)


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    category: str
    severity: Severity
    stack: list[str]
    description: str
    input: CaseInput
    ground_truth: GroundTruth
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    case_dir: Path | None = Field(default=None, exclude=True)


class CaseManifest(BaseModel):
    version: str
    name: str
    cases: list[str]


class Finding(BaseModel):
    title: str
    summary: str
    category: str
    severity: Severity
    file: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    evidence: str
    suggested_fix: str | None = None
    suggested_patch: str | None = None
    replacement_code: str | None = None
    patch_confidence: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)

    @field_validator("line_end")
    @classmethod
    def finding_end_not_before_start(cls, value: int, info: Any) -> int:
        start = info.data.get("line_start")
        if start is not None and value < start:
            raise ValueError("finding line_end cannot precede line_start")
        return value


class ReviewResult(BaseModel):
    findings: list[Finding]
    # The reviewer's single complete repair for the whole case. This is the only
    # patch Arena applies; per-finding ``suggested_patch`` is advisory and never
    # applied (combining finding patches has ambiguous order/overlap semantics).
    proposed_patch: str | None = None
    overall_risk: Risk
    review_summary: str


class ReviewerCaseMetadata(BaseModel):
    id: str
    title: str
    category: str
    severity: Severity
    stack: list[str]
    description: str


class CaseContext(BaseModel):
    case: ReviewerCaseMetadata
    diff: str
    relevant_files: dict[str, str]
    context_truncated: bool = False
    omitted_files: list[str] = Field(default_factory=list)
    test_output: str = ""
    static_analysis_output: str = ""
    case_dir: Path | None = None


class ReviewerResponse(BaseModel):
    raw_response: str
    parsed_response: ReviewResult | None = None
    invalid_output: bool = False
    parse_attempts: int = 1
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    tool_usage: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    concept_match: float = 0
    file_match: float = 0
    line_overlap: float = 0
    severity_match: float = 0
    fix_quality: float = 0
    no_false_positives: float = 0
    false_positive_penalty: float = 0
    invalid_json_penalty: float = 0
    total: float = 0


# A finding's status once execution evidence is in. "detected" is the pre-execution
# value; the runner upgrades it to repair_validated / detected_but_unrepaired.
FindingEvidence = Literal[
    "repair_validated", "detected_but_unrepaired", "unsupported", "neutral", "detected"
]
# A case's overall outcome after execution.
CaseStatus = Literal[
    "complete_repair",
    "partial_repair",
    "detected_but_unrepaired",
    "no_detection",
    "tampering",
    "inconclusive",
    "review_only",
]


class ScoredFinding(BaseModel):
    finding: Finding
    is_true_positive: bool
    matched_bug_index: int | None = None
    is_neutral: bool = False
    false_positive_reason: str | None = None
    evidence_status: FindingEvidence | None = None


class BugRepair(BaseModel):
    """Per-bug attribution: was it found by the reviewer, and did the patch fix it?"""

    bug_id: str
    detected: bool
    repaired: bool


class DeterministicCaseScore(BaseModel):
    case_id: str
    detected_bug: bool
    localized_correctly: bool
    patch_provided: bool
    patch_applied: bool
    tests_ran: bool
    tests_passed: bool | None = None
    structural_validation_ran: bool
    structural_validation_passed: bool | None = None
    true_positive_count: int
    false_positive_count: int
    false_negative_count: int
    precision: float
    recall: float
    f1: float
    f_beta: float
    patch_apply_score: float
    execution_score: float
    structural_score: float
    deterministic_pass: bool
    failure_reasons: list[str] = Field(default_factory=list)


class DeterministicMetrics(BaseModel):
    detection_precision: float = 0.0
    detection_recall: float = 0.0
    detection_f1: float = 0.0
    detection_f_beta: float = 0.0
    # DEPRECATED: validated_precision/f1/f_beta mix a case-level numerator
    # (validated cases) with a finding-level denominator (false-positive
    # findings), so they are not unit-coherent and are not comparable across
    # packs. They remain only so existing run JSON keeps loading. Use
    # validated_case_rate as the case-level repair metric instead; the unit-clean
    # per-finding/per-bug repair metrics arrive with the evidence layer.
    validated_precision: float = 0.0
    validated_recall: float = 0.0
    validated_f1: float = 0.0
    validated_f_beta: float = 0.0
    beta: float
    deterministic_pass_rate: float = 0.0
    # Canonical, unit-coherent case-level repair metric: validated cases over
    # eligible cases (numerically equal to deterministic_pass_rate, which stays
    # as a legacy alias). This is the default leaderboard sort.
    validated_case_rate: float = 0.0
    # Evidence-derived dimensions (see docs/v2-architecture.md sec 4.3):
    # Repair Success -- cases the patch fully repaired (case unit).
    complete_repair_rate: float = 0.0
    # Review Accuracy -- cases where every seeded bug was detected (case unit).
    bug_completeness_rate: float = 0.0
    # Review Trustworthiness -- of the findings that count (excluding neutral
    # acceptable findings), the fraction that matched a real bug (finding unit).
    supported_claim_rate: float | None = None
    localization_rate: float | None = None
    patch_apply_rate: float | None = None
    test_pass_rate: float | None = None
    structural_pass_rate: float | None = None
    false_positives_per_case: float
    cost_per_validated_fix: float | None = None
    latency_per_case_ms: float

    @model_validator(mode="before")
    @classmethod
    def load_legacy_metric_names(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        converted = dict(value)
        converted.setdefault("detection_precision", converted.get("precision", 0.0))
        converted.setdefault("detection_recall", converted.get("recall", 0.0))
        converted.setdefault("detection_f1", converted.get("f1", 0.0))
        converted.setdefault("detection_f_beta", converted.get("f_beta", 0.0))
        converted.setdefault("validated_precision", converted.get("precision", 0.0))
        converted.setdefault("validated_recall", converted.get("recall", 0.0))
        converted.setdefault("validated_f1", converted.get("f1", 0.0))
        converted.setdefault("validated_f_beta", converted.get("f_beta", 0.0))
        converted.setdefault("validated_case_rate", converted.get("deterministic_pass_rate", 0.0))
        converted.setdefault("latency_per_case_ms", converted.get("latency_per_case", 0.0))
        converted.setdefault("cost_per_validated_fix", converted.get("cost_per_true_positive"))
        return converted


class CaseResult(BaseModel):
    case_id: str
    title: str
    category: str
    severity: Severity
    ground_truth_summary: str
    response: ReviewerResponse
    scored_findings: list[ScoredFinding]
    breakdown: ScoreBreakdown
    score: float
    review_quality_score: float | None = None
    bug_found: bool
    correct_file: bool
    correct_line: bool
    line_match: str
    bugs_total: int = 1
    bugs_matched: int = 0
    false_positive_count: int
    context_truncated: bool = False
    test_output: str = ""
    deterministic_case_score: DeterministicCaseScore | None = None
    patch_provided: bool = False
    patch_applied: bool = False
    patch_error: str | None = None
    touched_files: list[str] = Field(default_factory=list)
    tests_ran: bool = False
    tests_passed: bool | None = None
    test_stdout_tail: str = ""
    test_stderr_tail: str = ""
    validators_run: list[str] = Field(default_factory=list)
    validators_passed: bool | None = None
    validator_results: list[dict[str, Any]] = Field(default_factory=list)
    deterministic_pass: bool | None = None
    failure_reasons: list[str] = Field(default_factory=list)
    raw_suggested_patch: str | None = None
    # Evidence attribution (populated in patch/full mode).
    case_status: CaseStatus | None = None
    bug_repairs: list[BugRepair] = Field(default_factory=list)
    # How this case actually executed (docker / trusted-local / none).
    execution_backend: ExecutionBackend = "none"


class RunMetadata(BaseModel):
    prompt_version: str
    benchmark_version: str
    temperature: float = 0.0
    git_commit: str | None = None
    pack_checksum: str | None = None
    # True/False when the pack ships a pack.sha256 to compare against; None otherwise.
    pack_checksum_verified: bool | None = None


class RunResult(BaseModel):
    run_id: str
    benchmark_set: str
    reviewer: str
    model: str | None
    started_at: datetime
    completed_at: datetime
    metadata: RunMetadata
    case_results: list[CaseResult]
    total_score: float
    budget_stopped_reason: str | None = None
    skipped_case_ids: list[str] = Field(default_factory=list)
    # Run validity and coverage. schema_version defaults to 1 so runs loaded from
    # pre-v2 JSON (which never carried these fields) read as legacy v1 and are
    # excluded from the v2 leaderboard; run_benchmark sets RUN_SCHEMA_VERSION.
    schema_version: int = 1
    run_status: RunStatus = "complete"
    execution_backend: ExecutionBackend = "none"
    eligible_case_count: int = 0
    completed_case_count: int = 0
    failed_case_count: int = 0
    skipped_case_count: int = 0
    coverage_rate: float = 1.0
    mode: Literal["review", "patch", "full"] = "review"
    beta: float = 1.0
    deterministic_metrics: DeterministicMetrics | None = None
    bugs_found: int
    correct_files: int
    correct_lines: int
    false_positives: int
    total_cost: float
    total_latency_ms: int

    @property
    def case_count(self) -> int:
        return len(self.case_results)
