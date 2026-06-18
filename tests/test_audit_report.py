import json
from datetime import UTC, datetime
from pathlib import Path

from arena.core.models import DeterministicMetrics, RunMetadata, RunResult
from arena.reports.audit_report import build_audit_report_data, write_audit_report
from arena.reports.json_report import write_json_report


def _sample_run(run_id: str, validated: float, detection: float) -> RunResult:
    metrics = DeterministicMetrics(
        detection_f_beta=detection,
        validated_f_beta=validated,
        beta=1.0,
        deterministic_pass_rate=validated,
        patch_apply_rate=1.0,
        test_pass_rate=1.0,
        structural_pass_rate=1.0,
        false_positives_per_case=0.0,
        cost_per_validated_fix=0.0,
        latency_per_case_ms=10.0,
    )
    return RunResult(
        run_id=run_id,
        benchmark_set="audit_v1",
        reviewer="mock",
        model="perfect_patch",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        metadata=RunMetadata(prompt_version="v1", benchmark_version="audit_v1"),
        case_results=[],
        total_score=100.0,
        mode="full",
        beta=1.0,
        deterministic_metrics=metrics,
        bugs_found=5,
        correct_files=5,
        correct_lines=5,
        false_positives=0,
        total_cost=0.0,
        total_latency_ms=50,
    )


def test_audit_report_empty_state(tmp_path: Path):
    data = build_audit_report_data([])
    assert data["empty"] is True
    assert data["summary"]["benchmark_pack"] == "audit_v1"
    markdown = write_audit_report(tmp_path, tmp_path / "report.md")
    assert markdown["empty"] is True


def test_audit_report_is_pack_agnostic():
    data = build_audit_report_data([], benchmark_set="audit_v2")
    assert data["summary"]["benchmark_pack"] == "audit_v2"
    assert "Audit Pack v2" in data["title"]
    assert any("audit_v2" in command for command in data["reproducibility_commands"])


def test_audit_report_uses_real_run_json_only(tmp_path: Path):
    run = _sample_run("audit-run-1", validated=0.5, detection=1.0)
    run_dir = tmp_path / "audit-run-1"
    run_dir.mkdir()
    write_json_report(run, run_dir / "run.json")
    (tmp_path / "other-set").mkdir()
    other = _sample_run("other", validated=1.0, detection=1.0)
    other = other.model_copy(update={"benchmark_set": "v1"})
    write_json_report(other, tmp_path / "other-set" / "run.json")

    from arena.reports.audit_report import load_audit_runs

    runs = load_audit_runs(tmp_path)
    data = build_audit_report_data(runs)
    assert data["empty"] is False
    assert len(data["reviewers"]) == 1
    assert data["reviewers"][0]["validated_f_beta"] == 0.5
    assert data["gaps"][0]["gap"] == 0.5

    output = tmp_path / "audit.md"
    json_path = tmp_path / "audit.json"
    payload = write_audit_report(tmp_path, output, json_path)
    assert output.exists()
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["title"].startswith("Detection Is Not Validation")
    assert "Limitations" in output.read_text(encoding="utf-8")
    assert payload["summary"]["run_count"] == 1


def test_audit_report_json_matches_schema_and_markdown(tmp_path: Path):
    from arena.core.config import REPORT_SCHEMA_VERSION
    from arena.reports.report_schema import AuditReport

    run = _sample_run("audit-run-1", validated=0.5, detection=1.0)
    run_dir = tmp_path / "audit-run-1"
    run_dir.mkdir()
    write_json_report(run, run_dir / "run.json")

    output = tmp_path / "audit.md"
    json_path = tmp_path / "audit.json"
    data = write_audit_report(tmp_path, output, json_path)

    # The written JSON validates against the versioned contract.
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    report = AuditReport.model_validate(saved)
    assert report.schema_version == REPORT_SCHEMA_VERSION

    # Markdown and JSON are rendered from one source, so the JSON's headline figure
    # appears verbatim in the Markdown table.
    markdown = output.read_text(encoding="utf-8")
    assert f"{data['reviewers'][0]['validated_f_beta']:.3f}" in markdown
    assert report.summary.reviewers_tested == data["summary"]["reviewers_tested"]


def test_audit_report_schema_rejects_drift():
    import pytest
    from pydantic import ValidationError

    from arena.reports.report_schema import AuditReport

    with pytest.raises(ValidationError):
        AuditReport.model_validate({"schema_version": "1.0", "unexpected": True})
