"""The generic adversarial baseline: localizes the bug but never repairs it."""

from pathlib import Path

from arena.benchmark.benchmark_runner import run_benchmark
from arena.reviewers.shallow_patch import ShallowPatchReviewer

AUDIT_V2 = Path("benchmark_sets/audit_v2")
V1 = Path("benchmark_sets/v1")


def test_shallow_patch_detects_every_bug_but_validates_none(tmp_path):
    run = run_benchmark(
        AUDIT_V2,
        ShallowPatchReviewer(),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="full",
        allow_local_execution=True,
    )
    assert run.deterministic_metrics is not None
    # Detection is strong: the bug is localized to the right file in every case.
    assert run.bugs_found == run.case_count
    assert run.deterministic_metrics.bug_completeness_rate == 1.0
    # Repair is hollow: the superficial patch applies cleanly but fixes nothing.
    assert run.deterministic_metrics.patch_apply_rate == 1.0
    assert run.deterministic_metrics.validated_case_rate == 0.0
    assert run.deterministic_metrics.complete_repair_rate == 0.0
    assert all(case.repair_confidence == "unvalidated" for case in run.case_results)


def test_no_op_patch_cannot_inflate_validated_rate_on_detection_only_cases(tmp_path):
    # Regression: v1 has cases with no executable gate (e.g. a Java case). A no-op
    # patch that merely applies must NOT count as a validated repair on them; the
    # headline metric is computed only over cases that can actually be validated.
    run = run_benchmark(
        V1,
        ShallowPatchReviewer(),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="full",
        allow_local_execution=True,
    )
    assert run.deterministic_metrics is not None
    assert run.deterministic_metrics.validated_case_rate == 0.0
    # Any case that "passed" with nothing executed would be the bug; none should.
    assert not any(
        case.deterministic_pass and case.case_status == "inconclusive" for case in run.case_results
    )


def test_shallow_patch_needs_no_per_case_configuration(tmp_path):
    # Unlike keyword_gamer, it works on a pack it has never seen, with no answer
    # tables: the file to point at comes from the shipped reference patch.
    run = run_benchmark(
        AUDIT_V2,
        ShallowPatchReviewer(),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="review",
    )
    assert run.bugs_found == run.case_count
