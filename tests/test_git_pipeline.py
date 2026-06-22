"""Phase 1D: adversarial tests for Git-authoritative patch application.

Git determines what actually changed; the patch text is never the authority.
"""

from __future__ import annotations

import itertools
import os
import stat
import sys
import tempfile

import pytest
from hypothesis import given
from hypothesis import strategies as st

from arena.patching import git_pipeline
from arena.patching import git_pipeline as gp
from arena.patching.git_pipeline import GitChange, _parse_raw_z, apply_patch

_counter = itertools.count()


def _make(tmp_path, files: dict[str, str], modes: dict[str, int] | None = None):
    n = next(_counter)
    src = tmp_path / f"src{n}"
    for rel, content in files.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="" disables newline translation so LF patches match on Windows too.
        path.write_text(content, encoding="utf-8", newline="")
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
        unique_by=lambda record: record[1],  # the parser rejects duplicate paths
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


# --------------------------------------------------------------------------- #
# Bounded Git output (real flooding/hanging helper process)                   #
# --------------------------------------------------------------------------- #


def _fake_ctx(tmp_path, timeout=60.0):
    return gp._GitContext(cwd=tmp_path, env=dict(os.environ), config=[], timeout=timeout, scrub=())


def _run_fake(tmp_path, script, monkeypatch, *, timeout=60.0, stdin=b""):
    monkeypatch.setattr(gp, "GIT", sys.executable)
    return gp._run_git(_fake_ctx(tmp_path, timeout), ["-c", script], stdin=stdin)


def test_stdout_flood_is_bounded_and_process_terminated(tmp_path, monkeypatch):
    # An effectively unbounded writer: if output were buffered before checking, this
    # would hang/OOM. Bounded reading terminates it at the ceiling and raises promptly.
    script = (
        "import sys\n"
        "buf = b'x' * (1024 * 1024)\n"
        "for _ in range(100000):\n"
        "    sys.stdout.buffer.write(buf)\n"
    )
    import time as _t

    start = _t.perf_counter()
    with pytest.raises(gp._GitRunError) as e:
        _run_fake(tmp_path, script, monkeypatch)
    assert e.value.reason == "git_output_too_large"
    assert _t.perf_counter() - start < 30  # terminated at the bound, not after all output


def test_stderr_flood_is_bounded(tmp_path, monkeypatch):
    script = "import sys\nfor _ in range(100000):\n    sys.stderr.buffer.write(b'e'*(1024*1024))\n"
    with pytest.raises(gp._GitRunError) as e:
        _run_fake(tmp_path, script, monkeypatch)
    assert e.value.reason == "git_output_too_large"


def test_combined_output_flood_is_bounded(tmp_path, monkeypatch):
    script = (
        "import sys\n"
        "for _ in range(100000):\n"
        "    sys.stdout.buffer.write(b'o'*(512*1024))\n"
        "    sys.stderr.buffer.write(b'e'*(512*1024))\n"
    )
    with pytest.raises(gp._GitRunError) as e:
        _run_fake(tmp_path, script, monkeypatch)
    assert e.value.reason == "git_output_too_large"


def test_valid_output_then_flood_is_rejected(tmp_path, monkeypatch):
    script = (
        "import sys\n"
        "sys.stdout.buffer.write(b'looks-valid\\n')\n"
        "for _ in range(100000):\n"
        "    sys.stdout.buffer.write(b'x'*(1024*1024))\n"
    )
    with pytest.raises(gp._GitRunError) as e:
        _run_fake(tmp_path, script, monkeypatch)
    assert e.value.reason == "git_output_too_large"


def test_hang_after_output_times_out(tmp_path, monkeypatch):
    script = (
        "import sys, time\n"
        "sys.stdout.buffer.write(b'partial')\n"
        "sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )
    with pytest.raises(gp._GitRunError) as e:
        _run_fake(tmp_path, script, monkeypatch, timeout=1.0)
    assert e.value.reason == "git_timeout"


@pytest.mark.skipif(os.name != "posix", reason="process-group kill is POSIX")
def test_child_process_is_terminated_with_the_group(tmp_path, monkeypatch):
    # Parent spawns a child then floods; terminating the group must stop both quickly.
    script = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "buf = b'x' * (1024 * 1024)\n"
        "for _ in range(100000):\n"
        "    sys.stdout.buffer.write(buf)\n"
    )
    import time as _t

    start = _t.perf_counter()
    with pytest.raises(gp._GitRunError):
        _run_fake(tmp_path, script, monkeypatch)
    assert _t.perf_counter() - start < 30


def test_stdin_is_delivered(tmp_path, monkeypatch):
    script = "import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    rc, out, err = _run_fake(tmp_path, script, monkeypatch, stdin=b"hello-stdin")
    assert rc == 0 and out == b"hello-stdin"


# --------------------------------------------------------------------------- #
# Timeout compatibility                                                       #
# --------------------------------------------------------------------------- #


def test_timeout_validation(tmp_path):
    src, dest = _make(tmp_path, {"app.py": "x = 1\n"})
    for bad in (0, -1, 10_000_000):
        with pytest.raises(ValueError):
            apply_patch(
                source_dir=src, patch_text="x", protected_paths=[], destination=dest, timeout=bad
            )


def test_patch_applier_passes_its_timeout(tmp_path, monkeypatch):
    from arena.patching.patch_applier import PatchApplier
    from arena.patching.patch_models import PatchApplyRequest

    captured = {}
    real = gp.apply_patch

    def spy(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        return real(*args, **kwargs)

    monkeypatch.setattr("arena.patching.patch_applier.apply_patch", spy)
    src, _ = _make(tmp_path, {"app.py": "x = 1\n"})
    PatchApplier(tmp_path / "runs", timeout_seconds=9).apply(
        PatchApplyRequest(case_id="c", source_dir=src, patch_text="", run_id="r")
    )
    assert captured["timeout"] == 9


# --------------------------------------------------------------------------- #
# Byte equivalence (baseline and result)                                      #
# --------------------------------------------------------------------------- #


def test_crlf_bytes_are_preserved_exactly(tmp_path):
    src, dest = _make(tmp_path, {"app.py": "def f():\n    return 1\n"})
    (src / "data.txt").write_bytes(b"a\r\nb\r\n")  # CRLF content
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
    r = apply_patch(source_dir=src, patch_text=patch, protected_paths=[], destination=dest)
    assert r.applied is True
    assert (r.workspace / "data.txt").read_bytes() == b"a\r\nb\r\n"  # no eol conversion


def test_baseline_gitattributes_is_rejected(tmp_path):
    src, dest = _make(tmp_path, {"app.py": "x = 1\n", ".gitattributes": "* text=auto\n"})
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    r = apply_patch(source_dir=src, patch_text=patch, protected_paths=[], destination=dest)
    assert r.applied is False
    assert r.reason == "baseline_index_failed"


def test_executable_baseline_file_round_trips(tmp_path):
    src, dest = _make(
        tmp_path, {"run.sh": "echo hi\n", "app.py": "x = 1\n"}, modes={"run.sh": 0o755}
    )
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    r = apply_patch(source_dir=src, patch_text=patch, protected_paths=[], destination=dest)
    assert r.applied is True


def test_blob_mismatch_fails_closed(tmp_path, monkeypatch):
    # If a worktree file's exact bytes do not hash to the index blob, the transaction
    # fails closed at the byte-equivalence check (baseline runs the same verification).
    monkeypatch.setattr(gp, "_raw_blob_id", lambda ctx, rel: "0" * 40)
    src, dest = _make(tmp_path, {"app.py": "x = 1\n"})
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    r = apply_patch(source_dir=src, patch_text=patch, protected_paths=[], destination=dest)
    assert r.applied is False
    assert r.reason in {"baseline_index_failed", "index_worktree_mismatch"}


def test_workspace_byte_change_after_apply_is_detected(tmp_path, monkeypatch):
    # Mutate a workspace file after git apply --index; the result byte-equivalence
    # check (independent of git status) must reject it.
    real = gp._check_status_clean

    def mutate(ctx):
        real(ctx)
        (ctx.cwd / "app.py").write_text("tampered = 1\n")

    monkeypatch.setattr(gp, "_check_status_clean", mutate)
    src, dest = _make(tmp_path, {"app.py": "def f():\n    return 1\n"})
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
    r = apply_patch(source_dir=src, patch_text=patch, protected_paths=[], destination=dest)
    assert r.applied is False
    assert r.reason == "index_worktree_mismatch"


# --------------------------------------------------------------------------- #
# Portable protected-path matching                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path,protected",
    [
        ("Conftest.py", []),
        ("PYPROJECT.TOML", []),
        ("Pkg/CONftest.py", []),
        ("Tests/test_x.py", ["tests"]),
        ("SRC/Hidden/x.py", ["src/hidden"]),
    ],
)
def test_protected_matching_is_case_insensitive(path, protected):
    assert gp.is_protected(path, protected) is True


def test_protected_matching_does_not_overmatch():
    assert gp.is_protected("app/main.py", ["tests"]) is False
    assert gp.is_protected("tests_helper/x.py", ["tests"]) is False  # component-wise, not prefix


def test_is_protected_path_helper_agrees(tmp_path):
    from arena.patching.patch_applier import is_protected_path

    assert is_protected_path("Conftest.py", []) is True
    assert is_protected_path("Tests/test_x.py", ["tests"]) is True
    assert is_protected_path("app/main.py", ["tests"]) is False


def test_rename_into_case_variant_protected_is_rejected(tmp_path):
    src, dest = _make(tmp_path, {"pkg/util.py": "x = 1\n", "app.py": "y = 1\n"})
    patch = (
        "diff --git a/pkg/util.py b/Conftest.py\n"
        "similarity index 100%\nrename from pkg/util.py\nrename to Conftest.py\n"
    )
    r = apply_patch(source_dir=src, patch_text=patch, protected_paths=[], destination=dest)
    assert r.applied is False
    assert r.reason == "protected_path_changed"


# --------------------------------------------------------------------------- #
# Hardened filesystem scan and metadata cleanup                               #
# --------------------------------------------------------------------------- #


def test_scan_rejects_symlinked_directory(tmp_path):
    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    (ws / "sub" / "a.py").write_text("x = 1\n")
    (tmp_path / "outside").mkdir()
    (ws / "link").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(gp._GitRunError) as e:
        gp._scan_workspace_files(ws)
    assert e.value.reason == "unsafe_result_entry"


def test_scan_rejects_residual_git_metadata_any_case(tmp_path):
    ws = tmp_path / "ws"
    (ws / ".GIT").mkdir(parents=True)
    (ws / ".GIT" / "config").write_text("[core]\n")
    with pytest.raises(gp._GitRunError) as e:
        gp._scan_workspace_files(ws)
    assert e.value.reason == "unsafe_result_entry"


def test_failed_git_cleanup_fails_closed(tmp_path, monkeypatch):
    real_rmtree = gp.shutil.rmtree

    def refuse(path, *args, **kwargs):
        if str(path).endswith(".git"):
            raise OSError("cannot remove")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(gp.shutil, "rmtree", refuse)
    src, dest = _make(tmp_path, {"app.py": "def f():\n    return 1\n"})
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n"
    r = apply_patch(source_dir=src, patch_text=patch, protected_paths=[], destination=dest)
    assert r.applied is False
    assert r.reason == "git_metadata_cleanup_failed"


# --------------------------------------------------------------------------- #
# Bounded diagnostics                                                         #
# --------------------------------------------------------------------------- #


def test_failure_carries_bounded_diagnostic_without_private_paths(tmp_path):
    src, dest = _make(tmp_path, {"app.py": "x = 1\n"})
    bad = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-nonexistent line\n+y\n"
    r = apply_patch(source_dir=src, patch_text=bad, protected_paths=[], destination=dest)
    assert r.applied is False and r.reason == "patch_preflight_failed"
    if r.diagnostic:
        assert len(r.diagnostic) <= 2048
        assert str(dest) not in r.diagnostic
        assert tempfile.gettempdir() not in r.diagnostic or "<private>" in r.diagnostic


# --------------------------------------------------------------------------- #
# Strict Git-output parsing (more malformed cases)                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "data",
    [
        b":100644 100644 aa bb X\0app.py\0",  # unknown status
        b":10064 100644 aa bb M\0app.py\0",  # malformed (5-digit) mode
        b":100644 100644 zz bb M\0app.py\0",  # non-hex sha
        b":100644 100644 aa bb M\0app.py\0:100644 100644 cc dd M\0app.py\0",  # duplicate path
        b":100644 100644 aa bb M\0app.py",  # missing final NUL
        b":100644 100644 aa bb M\0\0",  # empty path
    ],
)
def test_parse_raw_z_rejects_malformed(data):
    with pytest.raises(gp._GitRunError):
        gp._parse_raw_z(data)


@pytest.mark.parametrize(
    "data",
    [
        b"100644 " + b"a" * 40 + b" 0\tapp.py\0" + b"100644 " + b"b" * 40 + b" 0\tapp.py\0",  # dup
        b"100644 " + b"a" * 39 + b" 0\tapp.py\0",  # wrong-length sha
        b"100644 zz" + b"a" * 38 + b" 0\tapp.py\0",  # non-hex sha
        b"100644 " + b"a" * 40 + b" 1\tapp.py\0",  # unmerged stage
        b"1234 " + b"a" * 40 + b" 0\tapp.py\0",  # malformed (non-6-digit) mode
    ],
)
def test_parse_ls_files_rejects_malformed(data):
    with pytest.raises(gp._GitRunError):
        gp._parse_ls_files_z(data, "sha1")
