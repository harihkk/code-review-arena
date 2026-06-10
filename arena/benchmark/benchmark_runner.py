"""End-to-end benchmark run orchestration."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

from arena import __version__
from arena.benchmark.case_loader import build_context, load_cases, load_manifest
from arena.benchmark.pack_hash import pack_checksum, stored_checksum
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
from arena.scoring.scorer import apply_execution_fix_quality, score_case
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
    review_result = score_case(case, response, test_output=test_output).model_copy(
        update={"context_truncated": context.context_truncated}
    )
    if mode == "review":
        return review_result
    assert case.case_dir is not None
    matching_finding = next(
        (item.finding for item in review_result.scored_findings if item.matched_bug_index == 0),
        None,
    ) or next(
        (item.finding for item in review_result.scored_findings if item.is_true_positive), None
    )
    patch_text = matching_finding.suggested_patch if matching_finding else None
    protected_paths = list(case.validation.protected_paths)
    if case.input.tests_dir:
        protected_paths.append(case.input.tests_dir)
    patch = patch_applier.apply(
        PatchApplyRequest(
            case_id=case.id,
            source_dir=case.case_dir / case.input.after_dir,
            patch_text=patch_text or "",
            run_id=run_id,
            protected_paths=protected_paths,
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
    blocking = {
        "patch_required_but_missing",
        "patch_apply_failed",
        "tests_failed",
        "structural_validation_failed",
    }
    execution_validated = deterministic.patch_applied and not (
        blocking & set(deterministic.failure_reasons)
    )
    review_result = apply_execution_fix_quality(case, review_result, validated=execution_validated)
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
            false_negative_count=len(case.ground_truth.bugs),
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
        bugs_total=len(case.ground_truth.bugs),
        bugs_matched=0,
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
    max_wall_seconds: float | None = None,
    max_cost: float | None = None,
) -> RunResult:
    root = output_dir or runs_path()
    root.mkdir(parents=True, exist_ok=True)
    run_id, run_dir = _reserve_run_dir(root)
    manifest = load_manifest(benchmark_dir)
    checksum = pack_checksum(benchmark_dir)
    pinned = stored_checksum(benchmark_dir)
    started = datetime.now()
    case_results = []
    skipped_case_ids: list[str] = []
    budget_stopped_reason: str | None = None
    running_cost = 0.0
    test_executor = TestExecutor()
    patch_applier = PatchApplier(root)
    selected_beta = beta or 1.0
    for case in load_cases(benchmark_dir):
        if budget_stopped_reason is None:
            elapsed = (datetime.now() - started).total_seconds()
            if max_wall_seconds is not None and elapsed >= max_wall_seconds:
                budget_stopped_reason = (
                    f"max_wall_seconds={max_wall_seconds} exceeded after {elapsed:.1f}s"
                )
            elif max_cost is not None and running_cost >= max_cost:
                budget_stopped_reason = f"max_cost={max_cost} exceeded at {running_cost:.6f}"
        if budget_stopped_reason is not None:
            skipped_case_ids.append(case.id)
            continue
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
        running_cost += case_results[-1].response.estimated_cost
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
            pack_checksum=checksum,
            pack_checksum_verified=None if pinned is None else pinned == checksum,
        ),
        case_results=case_results,
        total_score=(
            round(sum(item.score for item in case_results) / len(case_results), 2)
            if case_results
            else 0.0
        ),
        budget_stopped_reason=budget_stopped_reason,
        skipped_case_ids=skipped_case_ids,
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
    _write_run_manifest(
        run_dir,
        run,
        reviewer,
        benchmark_dir,
        max_wall_seconds=max_wall_seconds,
        max_cost=max_cost,
    )
    shutil.copyfile(run_dir / "run.json", root / "latest.json")
    if persist:
        RunRepository(db_path or database_path()).save(run)
    return run


def _write_run_manifest(
    run_dir: Path,
    run: RunResult,
    reviewer: BaseReviewer,
    benchmark_dir: Path,
    *,
    max_wall_seconds: float | None,
    max_cost: float | None,
) -> None:
    """Everything needed to reproduce or audit the run, with secrets redacted."""
    payload = {
        "harness_version": __version__,
        "harness_git_commit": run.metadata.git_commit,
        "run_id": run.run_id,
        "benchmark_set": run.benchmark_set,
        "benchmark_dir": str(benchmark_dir),
        "pack_checksum": run.metadata.pack_checksum,
        "pack_checksum_verified": run.metadata.pack_checksum_verified,
        "prompt_version": run.metadata.prompt_version,
        "reviewer": {
            "identifier": reviewer.identifier,
            "name": reviewer.name,
            "model": reviewer.model,
            "config": reviewer.safe_config(),
        },
        "mode": run.mode,
        "beta": run.beta,
        "budgets": {"max_wall_seconds": max_wall_seconds, "max_cost": max_cost},
        "budget_stopped_reason": run.budget_stopped_reason,
        "skipped_case_ids": run.skipped_case_ids,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "cases": [
            {
                "case_id": case.case_id,
                "score": case.score,
                "deterministic_pass": case.deterministic_pass,
                "latency_ms": case.response.latency_ms,
                "estimated_cost": case.response.estimated_cost,
            }
            for case in run.case_results
        ],
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _tail(output: str, limit: int = 2000) -> str:
    return output[-limit:]
