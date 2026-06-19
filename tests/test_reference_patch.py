from pathlib import Path

import pytest

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.case_loader import build_context, load_cases
from arena.core.errors import ValidationError
from arena.core.registry import create_reviewer
from arena.patching.patch_applier import PatchApplier
from arena.patching.patch_models import PatchApplyRequest
from arena.reviewers.reference_patch import REFERENCE_PATCH_FILENAME, ReferencePatchReviewer


@pytest.fixture
def audit_benchmark_dir() -> Path:
    return Path("benchmark_sets/audit_v1")


def test_reference_patch_files_exist_for_audit_v1(audit_benchmark_dir: Path):
    cases = load_cases(audit_benchmark_dir)
    assert len(cases) == 10
    for case in cases:
        patch_path = case.case_dir / REFERENCE_PATCH_FILENAME
        assert patch_path.is_file(), f"missing {patch_path}"
        assert patch_path.read_text(encoding="utf-8").strip()


def test_reference_patch_files_apply_cleanly(audit_benchmark_dir: Path, tmp_path: Path):
    applier = PatchApplier(tmp_path / "runs")
    for case in load_cases(audit_benchmark_dir):
        patch_text = (case.case_dir / REFERENCE_PATCH_FILENAME).read_text(encoding="utf-8")
        result = applier.apply(
            PatchApplyRequest(
                case_id=case.id,
                source_dir=case.case_dir / case.input.after_dir,
                patch_text=patch_text,
                run_id=f"ref-{case.id}",
            )
        )
        assert result.applied is True, case.id


def test_reference_patch_reviewer_passes_audit_v1(audit_benchmark_dir: Path, tmp_path: Path):
    run = run_benchmark(
        audit_benchmark_dir,
        create_reviewer("reference-patch"),
        output_dir=tmp_path / "runs",
        db_path=tmp_path / "arena.db",
        mode="full",
        allow_local_execution=True,
    )
    metrics = run.deterministic_metrics
    assert metrics is not None
    assert metrics.validated_f_beta == 1
    assert metrics.detection_f_beta == 1
    assert metrics.deterministic_pass_rate == 1
    assert all(result.deterministic_pass for result in run.case_results)


def test_missing_reference_patch_aborts_the_run(audit_benchmark_dir: Path, tmp_path: Path):
    import shutil

    case = load_cases(audit_benchmark_dir)[0]
    bench_copy = tmp_path / "audit_copy"
    shutil.copytree(audit_benchmark_dir, bench_copy)
    (bench_copy / case.id / REFERENCE_PATCH_FILENAME).unlink()
    # The reviewer itself still degrades gracefully (no patch artifact to load).
    context = build_context(case).model_copy(update={"case_dir": bench_copy / case.id})
    finding = ReferencePatchReviewer().review(context).parsed_response.findings[0]
    assert finding.suggested_patch is None
    # But a pack missing a required reference.patch is invalid, so the run aborts
    # at validation rather than silently producing a failed case (mandatory-pack-
    # validation behavior). validate_case has always flagged this; it is now enforced.
    with pytest.raises(ValidationError):
        run_benchmark(
            bench_copy,
            create_reviewer("reference-patch"),
            output_dir=tmp_path / "runs",
            db_path=tmp_path / "arena.db",
            mode="full",
            allow_local_execution=True,
        )
