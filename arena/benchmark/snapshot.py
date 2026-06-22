"""Immutable benchmark-pack snapshots (Phase 1C).

Arena previously validated and hashed a mutable source pack and then re-read and
copied that same source for context, certification, mutation and execution, so a
source file could change between validation and use. This module makes one
accepted snapshot authoritative: a source pack is securely copied into a private
temporary tree, every regular file is mutation-checked and hashed, the tree is
sealed and checksummed, and every pack consumer reads only the snapshot. The
snapshot owns its temp directory and removes it on normal return and on errors.

This removes mutable-source time-of-check/time-of-use from Arena's OWN pack
consumers. It does not isolate the reviewer process, and an internally consistent
snapshot does not make a self-reported run official. Patch semantics remain Phase
1D. The source filesystem is treated as adversarial: changes are detected and the
operation fails closed rather than assuming races are impossible.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from arena.benchmark.pack_hash import pack_checksum, stored_checksum
from arena.core import limits
from arena.core.errors import SnapshotError

_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
_READ_CHUNK = 65536


@dataclass(frozen=True)
class SnapshotManifestEntry:
    """One regular file in the sealed snapshot."""

    path: str  # relative POSIX path
    size: int
    sha256: str
    mode: int  # execution-relevant permission bits (0o755 or 0o644)


@dataclass
class _CopyState:
    file_count: int = 0
    dir_count: int = 0
    total_bytes: int = 0
    manifest: list[SnapshotManifestEntry] = field(default_factory=list)
    # Normalized relative path -> original relative path, for collision detection.
    normalized: dict[str, str] = field(default_factory=dict)
    # (st_dev, st_ino) of regular files, for hardlink-alias detection.
    inodes: set[tuple[int, int]] = field(default_factory=set)
    # Original relative path -> identity captured during copy, for the post-scan.
    source_identity: dict[str, tuple[int, int, int]] = field(default_factory=dict)


def _normalized_key(relative: str) -> str:
    """Case-folded NFC key; collapses NFC, case-fold, and case-fold+NFC collisions."""
    return unicodedata.normalize("NFC", relative).casefold()


def _check_name_representable(name: str) -> None:
    # os.scandir surrogate-escapes undecodable bytes; such names cannot be encoded
    # to UTF-8 or persisted in JSON evidence, so reject them.
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SnapshotError(
            "unsupported_filename", "pack contains an undecodable filename"
        ) from exc


def _register(state: _CopyState, relative: str, *, is_dir: bool) -> None:
    key = _normalized_key(relative)
    existing = state.normalized.get(key)
    if existing is not None and existing != relative:
        raise SnapshotError(
            "path_collision",
            f"pack entries collide under Unicode/case normalization: {existing!r} and {relative!r}",
        )
    state.normalized[key] = relative


def _copy_file(
    src: Path, dst: Path, relative: str, state: _CopyState, lstat_info: os.stat_result
) -> None:
    if lstat_info.st_dev and lstat_info.st_ino:
        identity = (lstat_info.st_dev, lstat_info.st_ino)
        if identity in state.inodes:
            raise SnapshotError("hardlink_found", f"pack file is a hardlink alias: {relative!r}")
        state.inodes.add(identity)
    try:
        descriptor = os.open(src, _OPEN_FLAGS)
    except OSError as exc:
        # O_NOFOLLOW raises ELOOP if a symlink raced in after the lstat.
        raise SnapshotError(
            "file_changed_during_copy", f"could not open {relative!r} safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SnapshotError(
                "unsafe_file_type", f"pack entry is not a regular file: {relative!r}"
            )
        digest = hashlib.sha256()
        size = 0
        # Exclusive create: never overwrite an existing snapshot entry.
        out_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        out = os.open(dst, out_flags, 0o600)
        try:
            while True:
                chunk = os.read(descriptor, _READ_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limits.PACK_FILE_BYTES:
                    raise SnapshotError(
                        "total_bytes_exceeded",
                        f"pack file exceeds the per-file byte limit: {relative!r}",
                    )
                state.total_bytes += len(chunk)
                if state.total_bytes > limits.SNAPSHOT_MAX_TOTAL_BYTES:
                    raise SnapshotError("total_bytes_exceeded", "pack exceeds the total byte limit")
                digest.update(chunk)
                os.write(out, chunk)
        finally:
            os.close(out)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    # The opened descriptor's identity/size/mtime must not have changed mid-read.
    if (
        (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or before.st_size != size
        or (before.st_mtime_ns != after.st_mtime_ns)
    ):
        raise SnapshotError(
            "file_changed_during_copy", f"pack file changed while copying: {relative!r}"
        )
    # Preserve only the execute bit (deterministic 0o755 / 0o644).
    mode = 0o755 if before.st_mode & stat.S_IXUSR else 0o644
    os.chmod(dst, mode)
    state.file_count += 1
    if state.file_count > limits.SNAPSHOT_MAX_FILES:
        raise SnapshotError("file_count_exceeded", "pack exceeds the maximum file count")
    state.source_identity[relative] = (
        int(before.st_mtime_ns),
        before.st_size,
        before.st_ino,
    )
    state.manifest.append(
        SnapshotManifestEntry(path=relative, size=size, sha256=digest.hexdigest(), mode=mode)
    )


def _copy_tree(src_dir: Path, dst_dir: Path, prefix: str, depth: int, state: _CopyState) -> None:
    if depth > limits.SNAPSHOT_MAX_DEPTH:
        raise SnapshotError("path_too_deep", "pack path depth exceeds the limit")
    with os.scandir(src_dir) as entries:
        for entry in sorted(entries, key=lambda e: e.name):
            _check_name_representable(entry.name)
            relative = f"{prefix}{entry.name}"
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise SnapshotError("symlink_found", f"pack contains a symlink: {relative!r}")
            if stat.S_ISDIR(info.st_mode):
                _register(state, relative, is_dir=True)
                state.dir_count += 1
                if state.dir_count > limits.SNAPSHOT_MAX_DIRS:
                    raise SnapshotError(
                        "directory_count_exceeded", "pack exceeds the maximum directory count"
                    )
                child = dst_dir / entry.name
                os.mkdir(child)
                _copy_tree(Path(entry.path), child, f"{relative}/", depth + 1, state)
            elif stat.S_ISREG(info.st_mode):
                _register(state, relative, is_dir=False)
                _copy_file(Path(entry.path), dst_dir / entry.name, relative, state, info)
            else:
                raise SnapshotError(
                    "unsafe_file_type", f"pack contains an unsupported special file: {relative!r}"
                )


def _assert_source_unchanged(source: Path, state: _CopyState) -> None:
    """Re-scan the source after copying and reject any add/remove/type/identity change."""
    seen: set[str] = set()
    for current, _dirs, files in os.walk(source, followlinks=False):
        rel_dir = Path(current).relative_to(source)
        for name in files:
            relative = (rel_dir / name).as_posix()
            path = Path(current) / name
            try:
                info = path.lstat()
            except FileNotFoundError as exc:
                raise SnapshotError(
                    "tree_changed_during_copy", "a pack file disappeared during copy"
                ) from exc
            if not stat.S_ISREG(info.st_mode):
                # A regular file we copied was swapped for a symlink/special entry.
                raise SnapshotError(
                    "tree_changed_during_copy", "a pack file changed type during copy"
                )
            recorded = state.source_identity.get(relative)
            if recorded is None:
                raise SnapshotError("tree_changed_during_copy", "a pack file appeared during copy")
            if (int(info.st_mtime_ns), info.st_size, info.st_ino) != recorded:
                raise SnapshotError("tree_changed_during_copy", "a pack file changed during copy")
            seen.add(relative)
    if seen != set(state.source_identity):
        raise SnapshotError("tree_changed_during_copy", "the pack file set changed during copy")


@dataclass(frozen=True)
class PackSnapshot:
    """A sealed, verified, immutable copy of a source pack. Reads target the snapshot."""

    source: Path
    root: Path
    checksum: str
    stored_checksum: str | None
    manifest: tuple[SnapshotManifestEntry, ...]
    file_count: int
    dir_count: int
    total_bytes: int

    def load(self) -> list:
        from arena.benchmark.case_loader import load_cases

        return load_cases(self.root)

    def load_and_validate(self) -> list:
        from arena.benchmark.dataset_validator import load_and_validate_pack

        return load_and_validate_pack(self.root)

    def verify(self) -> None:
        """Recompute the checksum from the snapshot and reject any post-seal drift."""
        if pack_checksum(self.root) != self.checksum:
            raise SnapshotError(
                "snapshot_changed_after_sealing", "the snapshot changed after sealing"
            )


@contextmanager
def snapshot_pack(source: Path) -> Iterator[PackSnapshot]:
    """Securely copy ``source`` into a sealed, verified, self-cleaning snapshot.

    Usage::

        with snapshot_pack(source) as snap:
            cases = snap.load_and_validate()
            ...  # every read targets snap.root, never the mutable source
    """
    source = Path(source)
    try:
        root_info = source.lstat()
    except FileNotFoundError as exc:
        raise SnapshotError("source_missing", f"pack source does not exist: {source}") from exc
    if stat.S_ISLNK(root_info.st_mode):
        raise SnapshotError("root_symlink", f"pack source is a symlink: {source}")
    if not stat.S_ISDIR(root_info.st_mode):
        raise SnapshotError("unsafe_file_type", f"pack source is not a directory: {source}")

    temp_root = Path(tempfile.mkdtemp(prefix="arena-snapshot-"))
    try:
        snapshot_root = temp_root / "pack"
        os.mkdir(snapshot_root)
        state = _CopyState()
        _copy_tree(source, snapshot_root, "", 1, state)
        _assert_source_unchanged(source, state)
        if len(state.manifest) > limits.SNAPSHOT_MANIFEST_ENTRIES:
            raise SnapshotError(
                "file_count_exceeded", "pack exceeds the snapshot manifest entry limit"
            )
        snapshot = PackSnapshot(
            source=source,
            root=snapshot_root,
            checksum=pack_checksum(snapshot_root),
            stored_checksum=stored_checksum(snapshot_root),
            manifest=tuple(state.manifest),
            file_count=state.file_count,
            dir_count=state.dir_count,
            total_bytes=state.total_bytes,
        )
        yield snapshot
        # Belt-and-suspenders: confirm nothing mutated the snapshot during the
        # operation (consumers also verify before sealing their own evidence).
        snapshot.verify()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
