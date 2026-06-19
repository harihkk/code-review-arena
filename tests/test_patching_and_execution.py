import sys
from pathlib import Path

from arena.benchmark.case_loader import build_context, load_cases
from arena.execution.test_executor import TestExecutionRequest, TestExecutor
from arena.patching.patch_applier import PatchApplier
from arena.patching.patch_models import PatchApplyRequest
from arena.patching.patch_parser import touched_files
from arena.reviewers.controls import ControlReviewer
from arena.validators.base import ValidatorContext
from arena.validators.registry import get_validator


def _case(benchmark_dir):
    return load_cases(benchmark_dir)[0]


def test_valid_patch_applies_without_mutating_fixture(benchmark_dir, tmp_path, monkeypatch):
    case = _case(benchmark_dir)
    source = (case.case_dir / case.input.after_dir).resolve()
    original = (source / "app/routes/admin.py").read_text(encoding="utf-8")
    finding = (
        ControlReviewer("perfect_patch").review(build_context(case)).parsed_response.findings[0]
    )
    monkeypatch.chdir(tmp_path)
    result = PatchApplier(Path("runs")).apply(
        PatchApplyRequest(
            case_id=case.id,
            source_dir=source,
            patch_text=finding.suggested_patch,
            run_id="valid",
        )
    )
    assert result.applied is True
    assert result.touched_files == ["app/routes/admin.py"]
    assert "Depends(require_admin)" in (
        tmp_path / "runs/valid/workspaces/fastapi_auth_bypass_001/app/routes/admin.py"
    ).read_text(encoding="utf-8")
    assert (source / "app/routes/admin.py").read_text(encoding="utf-8") == original


def test_materialized_case_retries_an_interrupted_copy(benchmark_dir, monkeypatch):
    # A real model run lost three cases to EINTR raised mid-copytree under load;
    # the materializer must retry rather than drop the case.
    from arena.execution import sandbox

    case = _case(benchmark_dir)
    real_copytree = sandbox.shutil.copytree
    calls = {"n": 0}

    def flaky_copytree(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise InterruptedError(4, "Interrupted system call", str(src))
        return real_copytree(src, dst, *args, **kwargs)

    monkeypatch.setattr(sandbox.shutil, "copytree", flaky_copytree)
    monkeypatch.setattr(sandbox.time, "sleep", lambda _seconds: None)

    with sandbox.materialized_case(case) as root:
        assert root.is_dir()
        assert any(root.rglob("*.py"))
    assert calls["n"] >= 2  # first attempt raised EINTR, a retry recovered it


def test_malformed_patch_fails_and_normalizes_paths(benchmark_dir, tmp_path):
    case = _case(benchmark_dir)
    result = PatchApplier(tmp_path / "runs").apply(
        PatchApplyRequest(
            case_id=case.id,
            source_dir=case.case_dir / case.input.after_dir,
            patch_text="not a diff",
            run_id="bad",
        )
    )
    assert result.applied is False
    assert touched_files("--- a/a.py\n+++ b/a.py\n") == ["a.py"]


def test_negative_mock_patch_modes_expose_distinct_failures(benchmark_dir, tmp_path):
    case = _case(benchmark_dir)
    context = build_context(case)
    missing = ControlReviewer("detects_no_patch").review(context).parsed_response.findings[0]
    assert missing.suggested_patch is None
    malformed = ControlReviewer("malformed_patch").review(context).parsed_response.findings[0]
    malformed_result = PatchApplier(tmp_path / "runs").apply(
        PatchApplyRequest(
            case_id=case.id,
            source_dir=case.case_dir / case.input.after_dir,
            patch_text=malformed.suggested_patch,
            run_id="malformed",
        )
    )
    assert malformed_result.applied is False
    bad = ControlReviewer("bad_patch").review(context).parsed_response.findings[0]
    bad_result = PatchApplier(tmp_path / "runs").apply(
        PatchApplyRequest(
            case_id=case.id,
            source_dir=case.case_dir / case.input.after_dir,
            patch_text=bad.suggested_patch,
            run_id="bad",
        )
    )
    assert bad_result.applied is True
    validation = get_validator("fastapi_requires_admin_authorization").validate(
        ValidatorContext(
            case_id=case.id,
            workspace_path=Path(bad_result.workspace_path),
            changed_files=bad_result.touched_files,
            finding=bad,
            case_metadata=case,
        )
    )
    assert validation.passed is False
    noisy = ControlReviewer("false_positive_patch").review(context).parsed_response
    assert len(noisy.findings) == 2


def test_local_test_execution_requires_explicit_opt_in(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    request = TestExecutionRequest(
        case_id="case",
        workspace_path=workspace,
        test_command=[sys.executable, "-c", "print('passed')"],
        timeout_seconds=5,
    )
    blocked = TestExecutor().execute(request)
    assert blocked.ran is False
    assert blocked.error == "local_execution_disabled"
    executed = TestExecutor().execute(request.model_copy(update={"allow_local_execution": True}))
    assert executed.ran is True
    assert executed.passed is True


def test_local_test_execution_reports_failure_and_timeout(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    failed = TestExecutor().execute(
        TestExecutionRequest(
            case_id="case",
            workspace_path=workspace,
            test_command=[sys.executable, "-c", "raise SystemExit(2)"],
            timeout_seconds=5,
            allow_local_execution=True,
        )
    )
    assert failed.ran is True
    assert failed.passed is False
    assert failed.exit_code == 2
    timed_out = TestExecutor().execute(
        TestExecutionRequest(
            case_id="case",
            workspace_path=workspace,
            test_command=[sys.executable, "-c", "import time; time.sleep(2)"],
            timeout_seconds=1,
            allow_local_execution=True,
        )
    )
    assert timed_out.timed_out is True
