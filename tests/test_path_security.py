"""Adversarial path-containment tests for arena/security/paths.py and its callers."""

import pytest

from arena.core.errors import ValidationError
from arena.patching.patch_applier import PatchApplier
from arena.patching.patch_models import PatchApplyRequest
from arena.security.paths import (
    assert_safe_delete_target,
    resolve_under,
    validate_case_id,
    validate_relative_path,
)


def test_valid_case_id_accepted():
    assert validate_case_id("money_discount_rounding_001") == "money_discount_rounding_001"
    assert validate_case_id("2026-06-19_15-32-06")  # run-id shaped slug


def test_absolute_case_id_rejected():
    with pytest.raises(ValidationError):
        validate_case_id("/tmp/example")


def test_parent_traversal_case_id_rejected():
    for value in ("..", "../../example", "..foo"):
        with pytest.raises(ValidationError):
            validate_case_id(value)


def test_windows_drive_case_id_rejected():
    for value in ("C:\\example", r"\\server\share", "C:example"):
        with pytest.raises(ValidationError):
            validate_case_id(value)


def test_empty_nul_and_separator_case_ids_rejected():
    for value in ("", "a/b", "a\\b", "with\x00nul"):
        with pytest.raises(ValidationError):
            validate_case_id(value)


def test_relative_path_rejects_absolute_traversal_and_drive():
    for value in ("/etc/passwd", "../escape", "a/../../b", "C:thing", "back\\slash"):
        with pytest.raises(ValidationError):
            validate_relative_path(value)
    assert validate_relative_path("app/pricing.py") == "app/pricing.py"


def test_after_dir_cannot_escape_case(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    with pytest.raises(ValidationError):
        resolve_under(case_dir, "../../after")
    # A legitimate relative dir resolves inside the case.
    assert resolve_under(case_dir, "after") == (case_dir / "after").resolve()


def test_tests_dir_cannot_escape_case(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    with pytest.raises(ValidationError):
        resolve_under(case_dir, "/abs/tests")


def test_resolve_under_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError):
        resolve_under(root, "link/secret")


def test_safe_delete_refuses_runs_root(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    with pytest.raises(ValidationError):
        assert_safe_delete_target(root, root)


def test_safe_delete_refuses_target_outside_root(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    (tmp_path / "elsewhere").mkdir()
    with pytest.raises(ValidationError):
        assert_safe_delete_target(root, tmp_path / "elsewhere")


def test_safe_delete_refuses_symlink_escape(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "case"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError):
        assert_safe_delete_target(root, link)


def test_safe_delete_allows_contained_child(tmp_path):
    root = tmp_path / "workspaces"
    (root / "case_001").mkdir(parents=True)
    assert_safe_delete_target(root, root / "case_001")  # no raise


def test_protected_check_catches_rename_to_protected_file():
    # A pure "rename to conftest.py" has no +++ line, so the old touched_files
    # check missed it; the protected check must see every referenced path.
    from arena.patching.patch_applier import is_protected_path
    from arena.patching.patch_parser import referenced_paths, touched_files

    patch = "diff --git a/foo.py b/conftest.py\nrename from foo.py\nrename to conftest.py\n"
    assert "conftest.py" in referenced_paths(patch)
    assert any(is_protected_path(p, []) for p in referenced_paths(patch))
    assert "conftest.py" not in touched_files(patch)  # the gap the fix closes


def test_patch_applier_rejects_unsafe_case_id(tmp_path):
    # The applier must reject an escaping case id before it builds or deletes any
    # path (so no rmtree ever runs on the unsafe target).
    applier = PatchApplier(tmp_path / "runs")
    request = PatchApplyRequest(
        case_id="../../../etc",
        source_dir=tmp_path / "src",
        patch_text="",
        run_id="run1",
    )
    with pytest.raises(ValidationError):
        applier.apply(request)
