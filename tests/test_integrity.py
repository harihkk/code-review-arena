"""Tamper detection: content manifests catch changes to hidden tests/oracles."""

import os
import sys
from pathlib import Path

import pytest

from arena.benchmark.benchmark_runner import run_benchmark
from arena.benchmark.case_loader import load_case, load_cases
from arena.core.errors import ValidationError
from arena.core.models import BenchmarkCase, CaseContext, Finding, ReviewerResponse, ReviewResult
from arena.execution.integrity import (
    file_manifest,
    find_unsafe_files,
    manifest_changes,
    unsafe_entries,
)
from arena.execution.sandbox import materialized_case
from arena.execution.test_executor import TestExecutionRequest, TestExecutor
from arena.reviewers.base import BaseReviewer


def _case_with_after_dir(case_dir: Path) -> BenchmarkCase:
    case = BenchmarkCase.model_validate(
        {
            "id": "c",
            "title": "t",
            "category": "correctness",
            "severity": "high",
            "stack": ["python"],
            "description": "d",
            "input": {"after_dir": "after", "tests_dir": None},
            "ground_truth": {
                "bugs": [
                    {
                        "summary": "b",
                        "files": [{"path": "app.py", "line_ranges": [{"start": 1, "end": 1}]}],
                        "concepts": ["x"],
                    }
                ]
            },
        }
    )
    case.case_dir = case_dir
    return case


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_load_cases_rejects_a_symlinked_benchmark_root(tmp_path):
    real = tmp_path / "real_pack"
    real.mkdir()
    (real / "manifest.yaml").write_text("version: v\nname: n\ncases: []\n")
    link = tmp_path / "linked_pack"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValidationError, match="symlink"):
        load_cases(link)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_load_cases_rejects_a_symlinked_case_directory(tmp_path):
    # A valid case dir lives OUTSIDE the pack; a manifest entry points at it via a
    # symlink. find_unsafe_files would follow the symlinked root, so loading must
    # reject the symlinked case directory before reading anything.
    outside = tmp_path / "outside_case"
    (outside / "after").mkdir(parents=True)
    (outside / "after" / "app.py").write_text("x = 1\n")
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "manifest.yaml").write_text("version: v\nname: n\ncases: [case_001]\n")
    (pack / "case_001").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError, match="symlink"):
        load_cases(pack)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_materialized_case_refuses_a_symlink_that_slipped_into_the_workspace(tmp_path):
    # Simulate a symlink that bypassed admission: copytree preserves it, and the
    # workspace re-scan must refuse to execute rather than leave it for the test
    # command to follow out of the workspace.
    case_dir = tmp_path / "case"
    after = case_dir / "after"
    after.mkdir(parents=True)
    (after / "app.py").write_text("x = 1\n")
    (after / "link").symlink_to("/etc/hosts")
    with pytest.raises(ValidationError, match="unsafe"):
        with materialized_case(_case_with_after_dir(case_dir)):
            pass


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
    # A valid pack must ship a reference.patch when patch_required; the tamper
    # reviewer supplies its own patch, so this only satisfies validation.
    (case / "reference.patch").write_text(
        "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n"
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


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_admission_flags_symlink_named_like_a_cache_dir(tmp_path):
    # The bypass: a symlink named .pytest_cache was skipped before the symlink
    # check, so admission missed it and copytree would follow it out of the tree.
    (tmp_path / "ok.py").write_text("x = 1\n")
    (tmp_path / ".pytest_cache").symlink_to("/etc", target_is_directory=True)
    assert ".pytest_cache" in find_unsafe_files(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_admission_flags_symlink_inside_a_cache_dir(tmp_path):
    cache = tmp_path / ".pytest_cache"
    cache.mkdir()
    (cache / "escape").symlink_to("/etc/hosts")
    assert ".pytest_cache/escape" in find_unsafe_files(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_admission_flags_pycache_symlink(tmp_path):
    (tmp_path / "__pycache__").symlink_to("/tmp", target_is_directory=True)
    assert "__pycache__" in find_unsafe_files(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX FIFOs")
def test_admission_flags_fifo_inside_a_cache_dir(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    os.mkfifo(cache / "pipe")
    assert "__pycache__/pipe" in find_unsafe_files(tmp_path)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks")
def test_materializer_copy_does_not_follow_symlinks(tmp_path):
    from arena.execution.sandbox import _copytree_resilient

    secret = tmp_path / "secret.txt"
    secret.write_text("host-only data\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("x = 1\n")
    (src / "link").symlink_to(secret)
    dst = tmp_path / "dst"
    _copytree_resilient(src, dst)
    # The link is preserved as a link, not resolved into a regular file holding the
    # host file's contents (which is what follow-symlinks copying would have done).
    assert (dst / "link").is_symlink()


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
