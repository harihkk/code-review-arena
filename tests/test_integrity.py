"""Tamper detection: content manifests catch changes to hidden tests/oracles."""

import sys

import pytest

from arena.execution.integrity import file_manifest, manifest_changes, unsafe_entries
from arena.execution.test_executor import TestExecutionRequest, TestExecutor


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
