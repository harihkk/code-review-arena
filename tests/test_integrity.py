"""Tamper detection: content manifests catch changes to hidden tests/oracles."""

import sys
from pathlib import Path

import pytest

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.case_loader import load_case
from arena.core.errors import ValidationError
from arena.core.models import CaseContext, Finding, ReviewerResponse, ReviewResult
from arena.execution.integrity import (
    file_manifest,
    find_unsafe_files,
    manifest_changes,
    unsafe_entries,
)
from arena.execution.test_executor import TestExecutionRequest, TestExecutor
from arena.reviewers.base import BaseReviewer

TAMPER_PATCH = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n"


class _TamperReviewer(BaseReviewer):
    name = "tamper-test"
    model = "x"

    def review(self, context: CaseContext) -> ReviewerResponse:
        finding = Finding(
            title="value bug",
            summary="the app value is wrong",
            category="correctness",
            severity="high",
            file="app.py",
            line_start=1,
            line_end=1,
            evidence="value",
            confidence=0.9,
        )
        result = ReviewResult(
            findings=[finding],
            proposed_patch=TAMPER_PATCH,
            overall_risk="high",
            review_summary="value bug",
        )
        return ReviewerResponse(raw_response=result.model_dump_json(), parsed_response=result)


def _build_tamper_pack(root: Path) -> Path:
    pack = root / "pack"
    case = pack / "tamper_case"
    (case / "before").mkdir(parents=True)
    (case / "after").mkdir(parents=True)
    (case / "tests").mkdir(parents=True)
    (pack / "manifest.yaml").write_text("version: tamper_v1\nname: tamper\ncases: [tamper_case]\n")
    (case / "before" / "app.py").write_text("VALUE = 1\n")
    (case / "after" / "app.py").write_text("VALUE = 1\n")
    (case / "pr.diff").write_text(TAMPER_PATCH)
    (case / "tests" / "test_victim.py").write_text("def test_v():\n    assert True\n")
    # An attacker test rewrites a sibling test file when collected.
    (case / "tests" / "test_attacker.py").write_text(
        "from pathlib import Path\n"
        "Path(__file__).parent.joinpath('test_victim.py').write_text("
        "'def test_v():\\n    assert True  # rewritten\\n')\n"
        "def test_a():\n    assert True\n"
    )
    (case / "case.yaml").write_text(
        "id: tamper_case\n"
        "title: Tamper case\n"
        "category: correctness\n"
        "severity: high\n"
        "stack: [python]\n"
        "description: A case whose tests get rewritten during the run.\n"
        "input: {diff: pr.diff, before_dir: before, after_dir: after, tests_dir: tests}\n"
        "ground_truth:\n"
        "  bugs:\n"
        "    - summary: app value bug\n"
        "      files: [{path: app.py, line_ranges: [{start: 1, end: 1}]}]\n"
        "      concepts: [correctness]\n"
        "      must_mention: [value]\n"
        "      acceptable_fix_keywords: [value]\n"
        "execution: {run_tests: true, test_command: 'pytest -q tests', timeout_seconds: 60}\n"
        "validation: {patch_required: true, tests_required: true}\n"
    )
    return pack


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX local execution")
def test_tampering_case_is_excluded_from_aggregate_metrics(tmp_path):
    pack = _build_tamper_pack(tmp_path)
    run = run_benchmark(
        pack,
        _TamperReviewer(),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="full",
        allow_local_execution=True,
    )
    result = run.case_results[0]
    assert result.case_status == "tampering"
    assert "test_integrity_violation" in result.failure_reasons
    assert result.deterministic_pass is False
    # The P1 fix: the stored nested score must also reflect the violation, or the
    # aggregate would still count this as a validated fix.
    assert result.deterministic_case_score is not None
    assert result.deterministic_case_score.deterministic_pass is False
    assert "test_integrity_violation" in result.deterministic_case_score.failure_reasons
    assert run.deterministic_metrics is not None
    assert run.deterministic_metrics.validated_case_rate == 0.0
    assert run.deterministic_metrics.complete_repair_rate == 0.0


def test_manifest_is_stable_for_unchanged_files(tmp_path):
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "test_b.py").write_text("x = 1\n")
    first = file_manifest(tmp_path)
    assert set(first) == {"test_a.py", "sub/test_b.py"}
    assert manifest_changes(first, file_manifest(tmp_path)) == []


def test_manifest_detects_modify_create_delete(tmp_path):
    (tmp_path / "test_a.py").write_text("a\n")
    before = file_manifest(tmp_path)
    (tmp_path / "test_a.py").write_text("a-modified\n")
    (tmp_path / "test_new.py").write_text("new\n")
    changes = manifest_changes(before, file_manifest(tmp_path))
    assert "modified:test_a.py" in changes
    assert "created:test_new.py" in changes
    assert "deleted:test_a.py" in manifest_changes(before, {})


def test_manifest_ignores_caches_and_bytecode(tmp_path):
    (tmp_path / "test_a.py").write_text("a\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "test_a.cpython-312.pyc").write_text("bytecode\n")
    (tmp_path / "stray.pyc").write_text("x\n")
    assert set(file_manifest(tmp_path)) == {"test_a.py"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_manifest_flags_symlinks_as_unsafe(tmp_path):
    (tmp_path / "real.py").write_text("x\n")
    (tmp_path / "link.py").symlink_to(tmp_path / "real.py")
    manifest = file_manifest(tmp_path)
    assert manifest["link.py"] == "symlink"
    assert unsafe_entries(manifest) == ["link.py"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_find_unsafe_files_flags_symlinks(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\n")
    (tmp_path / "link.py").symlink_to("ok.py")
    unsafe = find_unsafe_files(tmp_path)
    assert "link.py" in unsafe
    assert "ok.py" not in unsafe


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_load_case_rejects_a_symlinked_pack(tmp_path):
    case = tmp_path / "evil_case"
    (case / "after").mkdir(parents=True)
    (case / "after" / "app.py").write_text("x = 1\n")
    (case / "after" / "sneaky.py").symlink_to("app.py")
    (case / "case.yaml").write_text(
        "id: evil_case\n"
        "title: Evil\n"
        "category: correctness\n"
        "severity: high\n"
        "stack: [python]\n"
        "description: A pack that smuggles a symlink.\n"
        "input: {after_dir: after}\n"
        "ground_truth:\n"
        "  bugs:\n"
        "    - summary: b\n"
        "      files: [{path: app.py, line_ranges: [{start: 1, end: 1}]}]\n"
        "      concepts: [correctness]\n"
    )
    with pytest.raises(ValidationError, match="unsafe"):
        load_case(case)


def test_tampering_during_execution_is_detected(tmp_path):
    victim = tmp_path / "test_victim.py"
    victim.write_text("def test_ok():\n    assert True\n")
    # An attacker test rewrites a sibling test file when collected.
    (tmp_path / "test_attacker.py").write_text(
        "from pathlib import Path\n"
        f"Path(r'{victim}').write_text('def test_ok():\\n    assert True  # rewritten\\n')\n"
        "def test_noop():\n    assert True\n"
    )
    before = file_manifest(tmp_path)
    TestExecutor().execute(
        TestExecutionRequest(
            case_id="c",
            workspace_path=tmp_path,
            test_command=[sys.executable, "-m", "pytest", "-q", str(tmp_path)],
            timeout_seconds=60,
            allow_local_execution=True,
        )
    )
    assert "modified:test_victim.py" in manifest_changes(before, file_manifest(tmp_path))
