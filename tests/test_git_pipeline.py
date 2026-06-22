"""Phase 1D: adversarial tests for Git-authoritative patch application.

Git determines what actually changed; the patch text is never the authority.
"""

from __future__ import annotations

import itertools
import os
import stat

import pytest
from hypothesis import given
from hypothesis import strategies as st

from arena.patching import git_pipeline
from arena.patching.git_pipeline import GitChange, _parse_raw_z, apply_patch

_counter = itertools.count()


def _make(tmp_path, files: dict[str, str], modes: dict[str, int] | None = None):
    n = next(_counter)
    src = tmp_path / f"src{n}"
    for rel, content in files.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if modes and rel in modes:
            os.chmod(path, modes[rel])
    return src, tmp_path / f"ws{n}"


def _apply(tmp_path, patch, *, files=None, protected=None, modes=None):
    files = files or {"app.py": "def f():\n    return 1\n", "pkg/util.py": "x = 1\n"}
    src, dest = _make(tmp_path, files, modes)
    return apply_patch(
        source_dir=src, patch_text=patch, protected_paths=protected or [], destination=dest
    )


# --------------------------------------------------------------------------- #
# Atomic application                                                          #
# --------------------------------------------------------------------------- #


def test_valid_patch_applies_authoritatively(tmp_path):
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
    r = _apply(tmp_path, patch)
    assert r.applied is True
    assert r.reason is None
    assert r.touched_files == ("app.py",)
    assert r.modified == ("app.py",)
    assert r.baseline_tree and r.result_tree and r.baseline_tree != r.result_tree
    assert r.object_format in {"sha1", "sha256"}
    assert r.patch_sha256 and len(r.patch_sha256) == 64
    assert not (r.workspace / ".git").exists()  # candidate never sees Git metadata
    assert (r.workspace / "app.py").read_text() == "def f():\n    return 2\n"


def test_one_invalid_hunk_fails_the_whole_transaction(tmp_path):
    # A valid hunk for app.py and a hunk that does not match pkg/util.py: the whole
    # patch must fail atomically, leave no partial result and no workspace.
    patch = (
        "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
        "--- a/pkg/util.py\n+++ b/pkg/util.py\n@@ -1 +1 @@\n-nonexistent\n+y = 9\n"
    )
    r = _apply(tmp_path, patch)
    assert r.applied is False
    assert r.reason in {"patch_preflight_failed", "patch_apply_failed"}
    assert r.workspace is None  # no executable workspace left behind


def test_no_reject_files_and_no_workspace_on_failure(tmp_path):
    r = _apply(tmp_path, "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-nope\n+x\n")
    assert r.applied is False and r.workspace is None


def test_empty_and_oversized_patches(tmp_path):
    assert _apply(tmp_path, "").reason == "no_patch_provided"
    assert _apply(tmp_path, "   \n").reason == "no_patch_provided"
    big = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-a\n+" + ("z" * (4 * 1024 * 1024 + 10)) + "\n"
    assert _apply(tmp_path, big).reason == "patch_too_large"


# --------------------------------------------------------------------------- #
# The handwritten parser never wins; Git does                                 #
# --------------------------------------------------------------------------- #


def test_misleading_plusplus_line_in_content_does_not_fool_authority(tmp_path):
    # The added content contains a line that looks like a diff header. The parser
    # might be confused; the authoritative result is exactly what Git changed.
    patch = (
        "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,4 @@\n def f():\n     return 1\n"
        "+# +++ b/conftest.py\n+# --- a/pyproject.toml\n"
    )
    r = _apply(tmp_path, patch)
    assert r.applied is True
    assert r.touched_files == ("app.py",)  # NOT conftest.py / pyproject.toml


# --------------------------------------------------------------------------- #
# Path operations                                                             #
# --------------------------------------------------------------------------- #


def test_add_modify_delete(tmp_path):
    add = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+created = 1\n"
    r = _apply(tmp_path, add)
    assert r.applied and r.added == ("new.py",)
    delete = "--- a/pkg/util.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x = 1\n"
    r = _apply(tmp_path, delete)
    assert r.applied and r.deleted == ("pkg/util.py",)


def test_rename_is_delete_plus_add_under_no_renames(tmp_path):
    patch = (
        "diff --git a/pkg/util.py b/pkg/renamed.py\n"
        "similarity index 100%\nrename from pkg/util.py\nrename to pkg/renamed.py\n"
    )
    r = _apply(tmp_path, patch)
    assert r.applied is True
    # With rename detection disabled, both endpoints are checked independently.
    assert set(r.added) == {"pkg/renamed.py"}
    assert set(r.deleted) == {"pkg/util.py"}


@pytest.mark.parametrize(
    "target",
    ["pyproject.toml", "conftest.py", "pkg/conftest.py", ".gitattributes", ".gitmodules"],
)
def test_creating_protected_files_is_rejected(tmp_path, target):
    patch = f"--- /dev/null\n+++ b/{target}\n@@ -0,0 +1 @@\n+x = 1\n"
    r = _apply(tmp_path, patch)
    assert r.applied is False
    # Protected basenames are rejected; the .git* ones are also dot-prefixed and so
    # may be caught first by the path policy. Either is a correct rejection.
    assert r.reason in {"protected_path_changed", "unsafe_result_path"}


def test_rename_into_protected_is_rejected(tmp_path):
    patch = (
        "diff --git a/pkg/util.py b/conftest.py\n"
        "similarity index 100%\nrename from pkg/util.py\nrename to conftest.py\n"
    )
    r = _apply(tmp_path, patch)
    assert r.applied is False
    assert r.reason == "protected_path_changed"


@pytest.mark.parametrize(
    "patch",
    [
        "--- a/../../escape.py\n+++ b/../../escape.py\n@@ -1 +1 @@\n-x\n+y\n",
        "--- /etc/passwd\n+++ /etc/passwd\n@@ -1 +1 @@\n-x\n+y\n",
        "--- /dev/null\n+++ b/.git/config\n@@ -0,0 +1 @@\n+[core]\n",
    ],
)
def test_unsafe_target_paths_are_rejected(tmp_path, patch):
    r = _apply(tmp_path, patch)
    assert r.applied is False
    assert r.reason in {
        "patch_preflight_failed",
        "patch_apply_failed",
        "unsafe_result_path",
        "protected_path_changed",
    }


# --------------------------------------------------------------------------- #
# Modes and entry types                                                       #
# --------------------------------------------------------------------------- #


def test_executable_new_file_is_allowed(tmp_path):
    patch = (
        "diff --git a/run.sh b/run.sh\nnew file mode 100755\n"
        "--- /dev/null\n+++ b/run.sh\n@@ -0,0 +1 @@\n+echo hi\n"
    )
    r = _apply(tmp_path, patch)
    assert r.applied is True
    assert any(c.new_mode == "100755" for c in r.changes)


def test_mode_only_change_is_recorded(tmp_path):
    patch = "diff --git a/app.py b/app.py\nold mode 100644\nnew mode 100755\n"
    r = _apply(tmp_path, patch)
    assert r.applied is True
    assert "app.py" in r.mode_changes


def test_symlink_mode_is_rejected(tmp_path):
    patch = (
        "diff --git a/link b/link\nnew file mode 120000\n"
        "--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+/etc/passwd\n\\ No newline at end of file\n"
    )
    r = _apply(tmp_path, patch)
    assert r.applied is False
    assert r.reason in {"unsafe_result_mode", "unsafe_result_entry"}


def test_gitlink_mode_is_rejected(tmp_path):
    patch = (
        "diff --git a/sub b/sub\nnew file mode 160000\n"
        "index 0000000..1234567890123456789012345678901234567890\n"
    )
    r = _apply(tmp_path, patch)
    assert r.applied is False  # gitlink/submodule rejected (mode or apply failure)


# --------------------------------------------------------------------------- #
# Git isolation from host configuration                                       #
# --------------------------------------------------------------------------- #


def test_hostile_global_git_config_is_ignored(tmp_path, monkeypatch):
    # A malformed/hostile global config would make Git error if it were read. The
    # pipeline builds a private env (empty global/system config, private HOME), so the
    # host config is never consulted and the transaction succeeds normally.
    hostile_home = tmp_path / "hostile_home"
    hostile_home.mkdir()
    (hostile_home / ".gitconfig").write_text(
        '[core]\n\teditor = sh -c "exit 7"\nthis is not valid git config {{{\n', encoding="utf-8"
    )
    monkeypatch.setenv("HOME", str(hostile_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile_home / ".gitconfig"))
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
    r = _apply(tmp_path, patch)
    assert r.applied is True  # host global config was not read


def test_git_env_and_config_are_isolated():
    from pathlib import Path

    env = git_pipeline._git_env(Path("/h"), Path("/h/cfg"), Path("/ceil"))
    assert env["HOME"] == "/h"
    assert env["GIT_CONFIG_GLOBAL"] == "/h/cfg"
    assert env["GIT_CONFIG_SYSTEM"] == "/h/cfg"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_ATTR_NOSYSTEM"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "USERPROFILE" not in env and "GIT_DIR" not in env
    joined = " ".join(git_pipeline._git_config(Path("/hooks")))
    for expected in (
        "core.hooksPath=/hooks",
        "core.autocrlf=false",
        "commit.gpgsign=false",
        "protocol.allow=never",
        "core.pager=",
    ):
        assert expected in joined


# --------------------------------------------------------------------------- #
# Raw-diff / ls-files parsing (unit + property)                               #
# --------------------------------------------------------------------------- #


def test_parse_raw_z_basic_and_malformed():
    data = b":100644 100644 aaa bbb M\0app.py\0:000000 100644 000 ccc A\0new.py\0"
    changes = _parse_raw_z(data)
    assert [c.status for c in changes] == ["M", "A"]
    assert changes[0].new_path == "app.py" and changes[1].new_path == "new.py"
    with pytest.raises(git_pipeline._GitRunError):
        _parse_raw_z(b"not-a-record\0path\0")
    with pytest.raises(git_pipeline._GitRunError):
        _parse_raw_z(b":100644 100644 aaa bbb M\0")  # truncated (no path)


@given(
    st.lists(
        st.tuples(
            st.sampled_from(["A", "M", "D", "T"]),
            st.text(alphabet="abcdefghij/_.", min_size=1, max_size=12),
        ),
        max_size=20,
    )
)
def test_parse_raw_z_roundtrip_property(records):
    blob = b""
    for status, path in records:
        blob += f":100644 100644 1111111 2222222 {status}".encode() + b"\0" + path.encode() + b"\0"
    parsed = _parse_raw_z(blob)
    assert [(c.status, c.new_path) for c in parsed] == records


def test_changes_are_frozen_records():
    import dataclasses

    change = GitChange("M", "100644", "100644", "a", "b", None, "x.py")
    with pytest.raises(dataclasses.FrozenInstanceError):
        change.status = "A"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Filesystem result scan                                                      #
# --------------------------------------------------------------------------- #


def test_result_workspace_has_only_regular_files(tmp_path):
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 3\n"
    r = _apply(tmp_path, patch)
    assert r.applied is True
    for current, _dirs, filenames in os.walk(r.workspace):
        for name in filenames:
            info = os.lstat(os.path.join(current, name))
            assert stat.S_ISREG(info.st_mode)
