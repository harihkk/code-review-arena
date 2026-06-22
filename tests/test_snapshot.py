"""Phase 1C: immutable pack snapshot traversal, mutation detection, and rewiring."""

from __future__ import annotations

import os
import shutil

import pytest

import arena.benchmark.snapshot as snap_mod
from arena.benchmark.pack_hash import pack_checksum, stored_checksum
from arena.benchmark.snapshot import snapshot_pack
from arena.core import limits
from arena.core.errors import SnapshotError

PACKS = ("v1", "audit_v1", "audit_v2")


def _pack(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree("benchmark_sets/audit_v2", pack)
    return pack


def _fs_keeps_distinct(directory, name_a, name_b) -> bool:
    """Whether this filesystem keeps two case/normalization-variant names distinct."""
    a, b = directory / name_a, directory / name_b
    try:
        a.write_text("a")
        b.write_text("b")
    except OSError:
        return False
    return a.exists() and b.exists() and a.read_text() == "a" and b.read_text() == "b"


# --------------------------------------------------------------------------- #
# Normal behavior                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", PACKS)
def test_shipped_pack_snapshots_validates_and_checksum_unchanged(name):
    from pathlib import Path

    source = Path("benchmark_sets") / name
    with snapshot_pack(source) as snap:
        cases = snap.load_and_validate()
        assert len(cases) == 10
        assert snap.checksum == pack_checksum(source) == stored_checksum(source)
        assert str(cases[0].case_dir).startswith(str(snap.root))
        snap.verify()


def test_source_modification_after_snapshot_does_not_affect_cases(tmp_path):
    pack = _pack(tmp_path)
    target = pack / "money_discount_rounding_001" / "after"
    a_file = next(p for p in target.rglob("*") if p.is_file())
    original = a_file.read_text(encoding="utf-8", errors="replace")
    with snapshot_pack(pack) as snap:
        cases = snap.load()
        case = next(c for c in cases if c.id == "money_discount_rounding_001")
        snap_file = case.case_dir / a_file.relative_to(pack / "money_discount_rounding_001")
        # Mutate (and then delete) the source after the snapshot was taken.
        a_file.write_text("TAMPERED = 1\n")
        assert snap_file.read_text(encoding="utf-8", errors="replace") == original
        shutil.rmtree(pack)
        assert snap_file.read_text(encoding="utf-8", errors="replace") == original
        snap.verify()  # source gone, snapshot intact


def test_cleanup_after_success_and_exception(tmp_path):
    pack = _pack(tmp_path)
    with snapshot_pack(pack) as snap:
        root = snap.root
        assert root.exists()
    assert not root.exists()  # cleaned on success

    with pytest.raises(RuntimeError):
        with snapshot_pack(pack) as snap:
            root = snap.root
            raise RuntimeError("boom")
    assert not root.exists()  # cleaned on exception too


def test_hidden_and_pycache_files_are_in_the_manifest(tmp_path):
    pack = _pack(tmp_path)
    (pack / ".hidden.py").write_text("X = 1\n")
    cache = pack / "money_discount_rounding_001" / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_bytes(b"\x00")
    with snapshot_pack(pack) as snap:
        paths = {entry.path for entry in snap.manifest}
    assert ".hidden.py" in paths
    assert "money_discount_rounding_001/__pycache__/x.pyc" in paths


# --------------------------------------------------------------------------- #
# Filesystem attacks                                                          #
# --------------------------------------------------------------------------- #


def _reason(excinfo) -> str:
    return excinfo.value.reason


def test_root_symlink_rejected(tmp_path):
    pack = _pack(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(pack, target_is_directory=True)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(link):
            pass
    assert _reason(e) == "root_symlink"


def test_missing_source_rejected(tmp_path):
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(tmp_path / "nope"):
            pass
    assert _reason(e) == "source_missing"


def test_file_symlink_rejected(tmp_path):
    pack = _pack(tmp_path)
    (pack / "evil.py").symlink_to("/etc/passwd")
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "symlink_found"


def test_directory_symlink_rejected(tmp_path):
    pack = _pack(tmp_path)
    (tmp_path / "outside").mkdir()
    (pack / "linkdir").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "symlink_found"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no mkfifo")
def test_fifo_rejected(tmp_path):
    pack = _pack(tmp_path)
    os.mkfifo(pack / "pipe")
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "unsafe_file_type"


@pytest.mark.skipif(not hasattr(os, "link"), reason="no hardlinks")
def test_hardlink_alias_rejected(tmp_path):
    pack = _pack(tmp_path)
    a = pack / "a.py"
    a.write_text("X = 1\n")
    try:
        os.link(a, pack / "b.py")
    except OSError:
        pytest.skip("filesystem does not support hardlinks")
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "hardlink_found"


def test_casefold_collision_rejected(tmp_path):
    pack = _pack(tmp_path)
    collide = pack / "collide"
    collide.mkdir()
    if not _fs_keeps_distinct(collide, "Foo.txt", "foo.txt"):
        pytest.skip("case-insensitive filesystem cannot hold both names")
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "path_collision"


def test_nfc_collision_rejected(tmp_path):
    pack = _pack(tmp_path)
    collide = pack / "collide"
    collide.mkdir()
    composed, decomposed = "é.py", "é.py"  # é vs e + combining acute
    if not _fs_keeps_distinct(collide, composed, decomposed):
        pytest.skip("normalization-insensitive filesystem cannot hold both names")
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "path_collision"


def test_excessive_file_count_rejected(tmp_path, monkeypatch):
    pack = _pack(tmp_path)
    monkeypatch.setattr(limits, "SNAPSHOT_MAX_FILES", 5)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "file_count_exceeded"


def test_excessive_directory_count_rejected(tmp_path, monkeypatch):
    pack = _pack(tmp_path)
    monkeypatch.setattr(limits, "SNAPSHOT_MAX_DIRS", 2)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "directory_count_exceeded"


def test_excessive_total_bytes_rejected(tmp_path, monkeypatch):
    pack = _pack(tmp_path)
    monkeypatch.setattr(limits, "SNAPSHOT_MAX_TOTAL_BYTES", 100)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "total_bytes_exceeded"


def test_excessive_depth_rejected(tmp_path, monkeypatch):
    pack = _pack(tmp_path)
    monkeypatch.setattr(limits, "SNAPSHOT_MAX_DEPTH", 1)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "path_too_deep"


def test_file_changed_during_copy_detected(tmp_path, monkeypatch):
    pack = _pack(tmp_path)
    real_fstat = os.fstat
    state = {"n": 0}

    class _Stat:
        def __init__(self, st, bump):
            self.st_mode = st.st_mode
            self.st_dev = st.st_dev
            self.st_ino = st.st_ino
            self.st_size = st.st_size
            self.st_mtime_ns = st.st_mtime_ns + bump

    def fake_fstat(fd):
        st = real_fstat(fd)
        state["n"] += 1
        # The "after" fstat (every even call) reports a later mtime -> change detected.
        return _Stat(st, 1 if state["n"] % 2 == 0 else 0)

    monkeypatch.setattr(snap_mod.os, "fstat", fake_fstat)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "file_changed_during_copy"


def test_tree_addition_during_copy_detected(tmp_path, monkeypatch):
    pack = _pack(tmp_path)
    real = snap_mod._copy_tree

    def wrapper(src_dir, dst_dir, prefix, depth, state):
        real(src_dir, dst_dir, prefix, depth, state)
        if prefix == "":  # after the whole tree is copied, a file appears at the source
            (pack / "sneaked_in.py").write_text("X = 1\n")

    monkeypatch.setattr(snap_mod, "_copy_tree", wrapper)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "tree_changed_during_copy"


def test_tree_removal_during_copy_detected(tmp_path, monkeypatch):
    pack = _pack(tmp_path)
    real = snap_mod._copy_tree
    victim = pack / "manifest.yaml"

    def wrapper(src_dir, dst_dir, prefix, depth, state):
        real(src_dir, dst_dir, prefix, depth, state)
        if prefix == "" and victim.exists():
            victim.unlink()

    monkeypatch.setattr(snap_mod, "_copy_tree", wrapper)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack):
            pass
    assert _reason(e) == "tree_changed_during_copy"


def test_snapshot_mutation_after_sealing_detected(tmp_path):
    pack = _pack(tmp_path)
    with pytest.raises(SnapshotError) as e:
        with snapshot_pack(pack) as snap:
            (snap.root / "injected.py").write_text("X = 1\n")  # tamper after sealing
            # context-exit verify() recomputes the checksum and rejects the drift
    assert _reason(e) == "snapshot_changed_after_sealing"


# --------------------------------------------------------------------------- #
# Integration                                                                 #
# --------------------------------------------------------------------------- #


def test_validate_cli_rejects_symlinked_pack(tmp_path):
    import typer

    from arena.cli.commands.validate import validate

    pack = _pack(tmp_path)
    (pack / "evil.py").symlink_to("/etc/passwd")
    with pytest.raises(typer.Exit) as e:
        validate(pack)
    assert e.value.exit_code == 1


def test_run_records_snapshot_metadata_and_round_trips(tmp_path):
    from pathlib import Path

    from arena.benchmark.benchmark_runner import run_benchmark
    from arena.core.models import RunResult
    from arena.core.registry import create_reviewer
    from arena.storage.repository import RunRepository

    run = run_benchmark(
        Path("benchmark_sets/audit_v1"),
        create_reviewer("control:perfect"),
        output_dir=tmp_path / "runs",
        db_path=tmp_path / "arena.db",
        mode="review",
    )
    assert run.metadata.snapshot_file_count == 84
    assert run.metadata.snapshot_integrity_verified is True
    assert run.metadata.snapshot_total_bytes and run.metadata.snapshot_total_bytes > 0
    # No temporary snapshot path leaks into persisted evidence.
    assert "arena-snapshot-" not in run.model_dump_json()
    repo = RunRepository(tmp_path / "arena.db")
    loaded = repo.get(run.run_id)
    assert isinstance(loaded, RunResult)
    assert loaded.metadata.snapshot_file_count == 84


def test_old_run_without_snapshot_metadata_loads():
    from datetime import datetime

    from arena.core.models import RunMetadata, RunResult

    run = RunResult(
        run_id="r",
        benchmark_set="v1",
        reviewer="control",
        model="perfect",
        started_at=datetime.now(),
        completed_at=datetime.now(),
        metadata=RunMetadata(prompt_version="v1", benchmark_version="v1"),
        case_results=[],
        total_score=0.0,
        bugs_found=0,
        correct_files=0,
        correct_lines=0,
        false_positives=0,
        total_cost=0.0,
        total_latency_ms=0,
    )
    assert run.metadata.snapshot_file_count is None
    assert run.metadata.snapshot_integrity_verified is None
