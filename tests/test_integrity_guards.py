"""Benchmark integrity guards: hostile patches, blind payloads, bounded context."""

import json
from pathlib import Path

import pytest

from arena.benchmark.case_loader import ContextLimits, build_context, load_cases
from arena.core.models import BenchmarkCase
from arena.patching.patch_applier import PatchApplier, is_protected_path
from arena.patching.patch_models import PatchApplyRequest, PatchApplyResult
from arena.patching.patch_parser import unsafe_patch_paths
from arena.reviewers.custom_command import serialize_reviewer_case
from arena.scoring.deterministic_scorer import score_deterministic_case
from arena.scoring.scorer import score_case
from tests.test_multi_bug_scoring import BUG0_FINDING, _case, _response

AUDIT_DIR = Path("benchmark_sets/audit_v1")


def _apply(tmp_path: Path, source_dir: Path, patch_text: str, **kwargs) -> PatchApplyResult:
    return PatchApplier(tmp_path / "runs").apply(
        PatchApplyRequest(
            case_id="case",
            source_dir=source_dir,
            patch_text=patch_text,
            run_id="hostile",
            **kwargs,
        )
    )


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app").mkdir()
    (source / "app" / "main.py").write_text("value = 1\n", encoding="utf-8")
    return source


def test_patch_touching_tests_dir_is_rejected(tmp_path, source_dir):
    # The protected file exists, so the patch applies cleanly and the AUTHORITATIVE
    # Git result (not the patch text) is what gets rejected as a protected change.
    (source_dir / "tests").mkdir()
    (source_dir / "tests" / "test_main.py").write_text("assert value == 2\n", encoding="utf-8")
    hostile = (
        "--- a/tests/test_main.py\n"
        "+++ b/tests/test_main.py\n"
        "@@ -1 +1 @@\n"
        "-assert value == 2\n"
        "+assert True\n"
    )
    result = _apply(tmp_path, source_dir, hostile, protected_paths=["tests"])
    assert result.applied is False
    assert result.reason == "protected_path_changed"
    assert "tests/test_main.py" in result.touched_protected


def test_patch_creating_conftest_is_rejected_anywhere(tmp_path, source_dir):
    hostile = "--- /dev/null\n+++ b/app/conftest.py\n@@ -0,0 +1 @@\n+import sys\n"
    result = _apply(tmp_path, source_dir, hostile)
    assert result.applied is False
    assert result.touched_protected == ["app/conftest.py"]


def test_patch_with_path_traversal_is_rejected(tmp_path, source_dir):
    hostile = "--- a/../../escape.py\n+++ b/../../escape.py\n@@ -1 +1 @@\n-x\n+y\n"
    result = _apply(tmp_path, source_dir, hostile)
    # Git itself refuses to apply a traversal path; the path guard is a backstop.
    assert result.applied is False
    assert result.reason in {"patch_preflight_failed", "unsafe_result_path"}


def test_patch_with_absolute_path_is_rejected(tmp_path, source_dir):
    hostile = "--- /etc/passwd\n+++ /etc/passwd\n@@ -1 +1 @@\n-x\n+y\n"
    result = _apply(tmp_path, source_dir, hostile)
    assert result.applied is False
    assert result.reason in {"patch_preflight_failed", "unsafe_result_path"}


def test_unsafe_paths_cover_renames():
    diff = "diff --git a/app/a.py b/../../b.py\nrename from app/a.py\nrename to ../../b.py\n"
    assert unsafe_patch_paths(diff) == ["../../b.py"]


def test_patch_creating_a_symlink_is_rejected(tmp_path, source_dir):
    # A mode-120000 diff makes git apply create a symlink, which could point
    # outside the workspace; the path-string guard alone would miss it.
    hostile = (
        "diff --git a/app/link b/app/link\n"
        "new file mode 120000\n"
        "--- /dev/null\n"
        "+++ b/app/link\n"
        "@@ -0,0 +1 @@\n"
        "+/etc/passwd\n"
    )
    result = _apply(tmp_path, source_dir, hostile)
    # Authoritative: the resulting Git mode is 120000 (a symlink), which is rejected.
    assert result.applied is False
    assert result.reason in {"unsafe_result_mode", "unsafe_result_entry"}


def test_protected_path_rules():
    assert is_protected_path("tests/test_x.py", ["tests"]) is True
    assert is_protected_path("conftest.py", []) is True
    assert is_protected_path("pyproject.toml", []) is True
    assert is_protected_path("app/main.py", ["tests"]) is False


def test_protected_patch_recorded_as_failure_reason():
    case = _case()
    review = score_case(case, _response([BUG0_FINDING]))
    patch = PatchApplyResult(
        case_id=case.id,
        applied=False,
        error="patch_touched_protected_files: tests/test_a.py",
        touched_files=["tests/test_a.py"],
        touched_protected=["tests/test_a.py"],
        workspace_path="unused",
        patch_text="--- a/tests/test_a.py\n+++ b/tests/test_a.py\n",
        duration_ms=1,
    )
    deterministic = score_deterministic_case(case, review, patch, None, [], beta=1.0)
    assert "patch_touched_protected_files" in deterministic.failure_reasons
    assert deterministic.deterministic_pass is False


def test_reviewer_payload_is_blind_by_default():
    case = load_cases(AUDIT_DIR)[0]
    context = build_context(case)
    payload = serialize_reviewer_case(context)
    for leaked in ("title", "description", "category", "severity"):
        assert leaked not in payload
    serialized = json.dumps(payload)
    assert case.title not in serialized
    assert case.description.strip().split(".")[0] not in serialized
    assert payload["case_id"] == case.id
    assert payload["pr_diff"]
    assert payload["relevant_files"]


def test_reveal_metadata_flag_restores_descriptive_fields():
    case = load_cases(AUDIT_DIR)[0]
    context = build_context(case)
    payload = serialize_reviewer_case(context, reveal_metadata=True)
    assert payload["title"] == case.title
    assert payload["severity"] == case.severity


def _disk_case(tmp_path: Path) -> BenchmarkCase:
    case_dir = tmp_path / "ctx_case"
    (case_dir / "after" / "app").mkdir(parents=True)
    (case_dir / "before").mkdir()
    (case_dir / "after" / "app" / "small.py").write_text("x = 1\n", encoding="utf-8")
    (case_dir / "after" / "app" / "big.py").write_text("y = 2\n" * 4000, encoding="utf-8")
    (case_dir / "pr.diff").write_text(
        "--- a/app/small.py\n+++ b/app/small.py\n@@ -1 +1 @@\n-x = 0\n+x = 1\n",
        encoding="utf-8",
    )
    case = _case()
    case.case_dir = case_dir
    return case


def test_context_is_bounded_and_prefers_diff_files(tmp_path):
    case = _disk_case(tmp_path)
    context = build_context(case, limits=ContextLimits(max_files=1))
    assert list(context.relevant_files) == ["app/small.py"]
    assert context.context_truncated is True
    assert context.omitted_files == ["app/big.py"]
    payload = serialize_reviewer_case(context)
    assert payload["context_truncated"] is True


def test_oversized_files_are_truncated_with_marker(tmp_path):
    case = _disk_case(tmp_path)
    context = build_context(case, limits=ContextLimits(max_file_bytes=64))
    assert "truncated by arena" in context.relevant_files["app/big.py"]
    assert context.context_truncated is True


def test_unbounded_context_is_not_marked_truncated(tmp_path):
    case = _disk_case(tmp_path)
    context = build_context(case)
    assert context.context_truncated is False
    assert context.omitted_files == []
    assert "context_truncated" not in serialize_reviewer_case(context)
