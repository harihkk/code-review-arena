"""Persistence operations for run results and API reads."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from arena.core.models import RunResult
from arena.storage.db import connect


class RunRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def save(self, run: RunResult) -> None:
        metrics = run.deterministic_metrics
        with connect(self.db_path) as db:
            db.execute(
                """INSERT OR REPLACE INTO runs
                   (id, reviewer, model, benchmark_set, started_at, completed_at,
                    total_score, total_cost, total_latency_ms, beta, deterministic_precision,
                    deterministic_recall, deterministic_f1, deterministic_f_beta,
                    detection_precision, detection_recall, detection_f1, detection_f_beta,
                    validated_precision, validated_recall, validated_f1, validated_f_beta,
                    deterministic_pass_rate,
                    patch_apply_rate, test_pass_rate, structural_pass_rate,
                    false_positives_per_case, cost_per_true_positive, cost_per_validated_fix,
                    latency_per_case_ms, run_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run.run_id,
                    run.reviewer,
                    run.model,
                    run.benchmark_set,
                    run.started_at.isoformat(),
                    run.completed_at.isoformat(),
                    run.total_score,
                    run.total_cost,
                    run.total_latency_ms,
                    run.beta,
                    metrics.detection_precision if metrics else None,
                    metrics.detection_recall if metrics else None,
                    metrics.detection_f1 if metrics else None,
                    metrics.detection_f_beta if metrics else None,
                    metrics.detection_precision if metrics else None,
                    metrics.detection_recall if metrics else None,
                    metrics.detection_f1 if metrics else None,
                    metrics.detection_f_beta if metrics else None,
                    metrics.validated_precision if metrics else None,
                    metrics.validated_recall if metrics else None,
                    metrics.validated_f1 if metrics else None,
                    metrics.validated_f_beta if metrics else None,
                    metrics.deterministic_pass_rate if metrics else None,
                    metrics.patch_apply_rate if metrics else None,
                    metrics.test_pass_rate if metrics else None,
                    metrics.structural_pass_rate if metrics else None,
                    metrics.false_positives_per_case if metrics else None,
                    metrics.cost_per_validated_fix if metrics else None,
                    metrics.cost_per_validated_fix if metrics else None,
                    metrics.latency_per_case_ms if metrics else None,
                    json.dumps(run.model_dump(mode="json")),
                ),
            )
            db.execute("DELETE FROM case_results WHERE run_id = ?", (run.run_id,))
            for case in run.case_results:
                case_result_id = str(uuid.uuid4())
                parsed = (
                    json.dumps(case.response.parsed_response.model_dump())
                    if case.response.parsed_response
                    else None
                )
                db.execute(
                    """INSERT INTO case_results
                   (id, run_id, case_id, score, bug_found, correct_file, correct_line,
                        false_positive_count, deterministic_pass, patch_provided, patch_applied,
                        tests_ran, tests_passed, structural_validation_ran,
                        structural_validation_passed, failure_reasons_json, patch_error,
                        raw_response, parsed_response)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        case_result_id,
                        run.run_id,
                        case.case_id,
                        case.score,
                        case.bug_found,
                        case.correct_file,
                        case.correct_line,
                        case.false_positive_count,
                        case.deterministic_pass,
                        case.patch_provided,
                        case.patch_applied,
                        case.tests_ran,
                        case.tests_passed,
                        bool(case.validators_run),
                        case.validators_passed,
                        json.dumps(case.failure_reasons),
                        case.patch_error,
                        case.response.raw_response,
                        parsed,
                    ),
                )
                for item in case.scored_findings:
                    finding = item.finding
                    db.execute(
                        """INSERT INTO findings
                           (id, case_result_id, title, category, severity, file, line_start,
                            line_end, summary, suggested_fix, confidence, is_true_positive)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            str(uuid.uuid4()),
                            case_result_id,
                            finding.title,
                            finding.category,
                            finding.severity,
                            finding.file,
                            finding.line_start,
                            finding.line_end,
                            finding.summary,
                            finding.suggested_fix or "",
                            finding.confidence,
                            item.is_true_positive,
                        ),
                    )
                for validator in case.validator_results:
                    db.execute(
                        """INSERT INTO validator_results
                           (id, case_result_id, validator_name, passed, confidence, message,
                            evidence_json, error)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            str(uuid.uuid4()),
                            case_result_id,
                            validator["name"],
                            validator["passed"],
                            validator["confidence"],
                            validator["message"],
                            json.dumps(validator["evidence"]),
                            validator.get("error"),
                        ),
                    )

    def list_runs(self) -> list[dict[str, object]]:
        with connect(self.db_path) as db:
            rows = db.execute(
                "SELECT id, reviewer, model, benchmark_set, total_score, total_cost, "
                "total_latency_ms, completed_at, beta, deterministic_precision, "
                "deterministic_recall, deterministic_f1, deterministic_f_beta, patch_apply_rate, "
                "test_pass_rate, structural_pass_rate, false_positives_per_case, "
                "cost_per_true_positive, detection_precision, detection_recall, detection_f1, "
                "detection_f_beta, validated_precision, validated_recall, validated_f1, "
                "validated_f_beta, deterministic_pass_rate, cost_per_validated_fix, "
                "latency_per_case_ms FROM runs ORDER BY completed_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, run_id: str) -> RunResult | None:
        with connect(self.db_path) as db:
            row = db.execute("SELECT run_json FROM runs WHERE id = ?", (run_id,)).fetchone()
        return RunResult.model_validate_json(row["run_json"]) if row else None

    def leaderboard(self) -> list[dict[str, object]]:
        with connect(self.db_path) as db:
            rows = db.execute("SELECT run_json FROM runs ORDER BY completed_at DESC").fetchall()
        latest: dict[tuple[str, str | None, str], RunResult] = {}
        history: dict[tuple[str, str | None, str], int] = {}
        for row in rows:
            run = RunResult.model_validate_json(row["run_json"])
            key = (run.reviewer, run.model, run.mode)
            history[key] = history.get(key, 0) + 1
            latest.setdefault(key, run)
        return [
            {
                "reviewer": run.reviewer,
                "model": run.model or "",
                "mode": run.mode,
                "benchmark_set": run.benchmark_set,
                "score": run.total_score,
                "bugs_found": run.bugs_found,
                "case_count": run.case_count,
                "false_positives": run.false_positives,
                "cost": run.total_cost,
                "latency_ms": run.total_latency_ms,
                "run_id": run.run_id,
                "history_count": history[key],
                "completed_at": run.completed_at.isoformat(),
                "deterministic_passes": sum(
                    result.deterministic_pass is True for result in run.case_results
                ),
                "deterministic_metrics": (
                    run.deterministic_metrics.model_dump() if run.deterministic_metrics else None
                ),
            }
            for key, run in sorted(
                latest.items(),
                key=lambda item: (
                    item[1].deterministic_metrics.validated_f_beta
                    if item[1].deterministic_metrics
                    else -1
                ),
                reverse=True,
            )
        ]
