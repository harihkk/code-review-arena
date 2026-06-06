"""End-to-end benchmark run orchestration."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

from arena.benchmark.case_loader import build_context, load_cases, load_manifest
from arena.core.config import PROMPT_VERSION, database_path, runs_path
from arena.core.models import (
    BenchmarkCase,
    CaseResult,
    DeterministicCaseScore,
    ReviewerResponse,
    RunMetadata,
    RunResult,
    ScoreBreakdown,
)
from arena.execution.sandbox import materialized_case
from arena.execution.test_executor import TestExecutionRequest, TestExecutionResult, TestExecutor
from arena.patching.patch_applier import PatchApplier
from arena.patching.patch_models import PatchApplyRequest
from arena.reports.html_report import write_html_report
from arena.reports.json_report import write_json_report
from arena.reports.markdown_report import write_markdown_report
from arena.reviewers.base import BaseReviewer
from arena.scoring.deterministic_scorer import (
    aggregate_deterministic_metrics,
    score_deterministic_case,
)
from arena.scoring.scorer import score_case
from arena.storage.repository import RunRepository
from arena.tools.static_analyzer import run_static_analysis
from arena.validators.base import ValidatorContext
from arena.validators.registry import run_validators


def _git_commit() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _reserve_run_dir(root: Path) -> tuple[str, Path]:
    base = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    candidate = base
    suffix = 1
    while True:
        run_dir = root / candidate
        try:
            run_dir.mkdir(parents=True)
            return candidate, run_dir
        except FileExistsError:
            candidate = f"{base}_{suffix}"
            suffix += 1


def _evaluate_case(
    case: BenchmarkCase,
    reviewer: BaseReviewer,
    *,
    test_executor: TestExecutor,
    patch_applier: PatchApplier,
    run_id: str,
    mode: Literal["review", "patch", "full"],
    selected_beta: float,
    allow_local_execution: bool,
) -> CaseResult:
    test_output = ""
    static_output = ""
    with materialized_case(case) as materialized:
        if allow_local_execution and case.execution.run_tests and case.execution.test_command:
            executed = test_executor.execute(
                TestExecutionRequest(
                    case_id=case.id,
                    workspace_path=materialized,
                    test_command=case.execution.test_command,
                    timeout_seconds=case.execution.timeout_seconds,
                    docker_image=case.execution.docker_image,
                    allow_local_execution=allow_local_execution,
                )
            )
            test_output = (
                f"exit_code={executed.exit_code}\nduration_ms={executed.duration_ms}\n"
                f"{executed.stdout}{executed.stderr}"
            )
        if case.execution.run_static_analysis and case.execution.static_analysis_command:
            static_output = run_static_analysis(
                materialized,
                case.execution.static_analysis_command,
                case.execution.timeout_seconds,
            )
    context = build_context(case, test_output=test_output, static_analysis_output=static_output)
    response = reviewer.review(context)
    review_result = score_case(case, response, test_output=test_output)
    if mode == "review":
        return review_result
    assert case.case_dir is not None
    matching_finding = next(
        (item.finding for item in review_result.scored_findings if item.is_true_positive), None
    )
    patch_text = matching_finding.suggested_patch if matching_finding else None
    patch = patch_applier.apply(
        PatchApplyRequest(
            case_id=case.id,
            source_dir=case.case_dir / case.input.after_dir,
            patch_text=patch_text or "",
            run_id=run_id,
        )
    )
    executed_tests: TestExecutionResult | None = None
    if patch.applied and case.execution.run_tests and case.execution.test_command:
        tests_dir = case.input.tests_dir
        if tests_dir and (case.case_dir / tests_dir).is_dir():
            shutil.copytree(
                case.case_dir / tests_dir,
                Path(patch.workspace_path) / tests_dir,
                dirs_exist_ok=True,
            )
        executed_tests = test_executor.execute(
            TestExecutionRequest(
                case_id=case.id,
                workspace_path=Path(patch.workspace_path),
                test_command=case.execution.test_command,
                timeout_seconds=case.execution.timeout_seconds,
                docker_image=case.execution.docker_image,
                allow_local_execution=allow_local_execution,
            )
        )
    validators = []
    if patch.applied and case.validation.structural_validators:
        validators = run_validators(
            case.validation.structural_validators,
            ValidatorContext(
                case_id=case.id,
                workspace_path=Path(patch.workspace_path),
                changed_files=patch.touched_files,
                finding=matching_finding,
                case_metadata=case,
            ),
        )
    deterministic = score_deterministic_case(
        case, review_result, patch, executed_tests, validators, selected_beta
    )
    return review_result.model_copy(
        update={
            "deterministic_case_score": deterministic,
            "patch_provided": deterministic.patch_provided,
            "patch_applied": deterministic.patch_applied,
            "patch_error": patch.error,
            "touched_files": patch.touched_files,
            "tests_ran": deterministic.tests_ran,
            "tests_passed": deterministic.tests_passed,
            "test_stdout_tail": _tail(executed_tests.stdout if executed_tests else ""),
            "test_stderr_tail": _tail(
                (executed_tests.stderr or executed_tests.error or "") if executed_tests else ""
            ),
            "validators_run": [item.name for item in validators],
            "validators_passed": deterministic.structural_validation_passed,
            "validator_results": [item.model_dump() for item in validators],
            "deterministic_pass": deterministic.deterministic_pass,
            "failure_reasons": deterministic.failure_reasons,
            "raw_suggested_patch": patch_text,
        }
    )


def _failed_case_result(
    case: BenchmarkCase,
    error: Exception,
    mode: Literal["review", "patch", "full"],
) -> CaseResult:
    """Record an unexpected per-case failure as a non-passing result and keep going."""
    reasons = [f"case_execution_error: {type(error).__name__}: {error}"]
    deterministic = None
    if mode != "review":
        deterministic = DeterministicCaseScore(
            case_id=case.id,
            detected_bug=False,
            localized_correctly=False,
            patch_provided=False,
            patch_applied=False,
            tests_ran=False,
            tests_passed=None,
            structural_validation_ran=False,
            structural_validation_passed=None,
            true_positive_count=0,
            false_positive_count=0,
            false_negative_count=1,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            f_beta=0.0,
            patch_apply_score=0.0,
            execution_score=0.0,
            structural_score=0.0,
            deterministic_pass=False,
            failure_reasons=reasons,
        )
    return CaseResult(
        case_id=case.id,
        title=case.title,
        category=case.category,
        severity=case.severity,
        ground_truth_summary=case.ground_truth.primary_bug.summary,
        response=ReviewerResponse(raw_response="", invalid_output=True),
        scored_findings=[],
        breakdown=ScoreBreakdown(),
        score=0.0,
        review_quality_score=0.0,
        bug_found=False,
        correct_file=False,
        correct_line=False,
        line_match="wrong_file",
        false_positive_count=0,
        deterministic_case_score=deterministic,
        deterministic_pass=False if mode != "review" else None,
        failure_reasons=reasons,
    )


def run_benchmark(
    benchmark_dir: Path,
    reviewer: BaseReviewer,
    output_dir: Path | None = None,
    db_path: Path | None = None,
    persist: bool = True,
    mode: Literal["review", "patch", "full"] = "review",
    beta: float | None = None,
    allow_local_execution: bool = False,
) -> RunResult:
    root = output_dir or runs_path()
    root.mkdir(parents=True, exist_ok=True)
    run_id, run_dir = _reserve_run_dir(root)
    manifest = load_manifest(benchmark_dir)
    started = datetime.now()
    case_results = []
    test_executor = TestExecutor()
    patch_applier = PatchApplier(root)
    selected_beta = beta or 1.0
    for case in load_cases(benchmark_dir):
        if beta is None:
            selected_beta = case.metrics.beta
        try:
            case_results.append(
                _evaluate_case(
                    case,
                    reviewer,
                    test_executor=test_executor,
                    patch_applier=patch_applier,
                    run_id=run_id,
                    mode=mode,
                    selected_beta=selected_beta,
                    allow_local_execution=allow_local_execution,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one failing case must not abort the batch.
            case_results.append(_failed_case_result(case, exc, mode))
    completed = datetime.now()
    total_cost = round(sum(item.response.estimated_cost for item in case_results), 6)
    total_latency = sum(item.response.latency_ms for item in case_results)
    run = RunResult(
        run_id=run_id,
        benchmark_set=manifest.version,
        reviewer=reviewer.name,
        model=reviewer.model,
        started_at=started,
        completed_at=completed,
        metadata=RunMetadata(
            prompt_version=PROMPT_VERSION,
            benchmark_version=manifest.version,
            git_commit=_git_commit(),
        ),
        case_results=case_results,
        total_score=round(sum(item.score for item in case_results) / len(case_results), 2),
        mode=mode,
        beta=selected_beta,
        deterministic_metrics=(
            aggregate_deterministic_metrics(case_results, selected_beta, total_cost, total_latency)
            if mode != "review"
            else None
        ),
        bugs_found=sum(item.bug_found for item in case_results),
        correct_files=sum(item.correct_file for item in case_results),
        correct_lines=sum(item.correct_line for item in case_results),
        false_positives=sum(item.false_positive_count for item in case_results),
        total_cost=total_cost,
        total_latency_ms=total_latency,
    )
    write_json_report(run, run_dir / "run.json")
    write_markdown_report(run, run_dir / "report.md")
    write_html_report(run, run_dir / "report.html")
    shutil.copyfile(run_dir / "run.json", root / "latest.json")
    if persist:
        RunRepository(db_path or database_path()).save(run)
    return run


def _tail(output: str, limit: int = 2000) -> str:
    return output[-limit:]
