"""Immutable benchmark-pack snapshots (Phase 1C).

Arena previously validated and hashed a mutable source pack and then re-read and
copied that same source for context, certification, mutation and execution, so a
source file could change between validation and use. This module makes one
accepted snapshot authoritative: a source pack is securely copied into a private
temporary tree, every regular file is mutation-checked, copied with a complete
write, re-read and hashed, and the tree is sealed with TWO distinct identities --

- the public pack checksum (sorted relative POSIX path, NUL, exact bytes, NUL),
  covering every regular file except the root ``pack.sha256``; and
- a full snapshot-manifest digest covering every file AND directory (including the
  root ``pack.sha256`` and empty directories) with sizes, per-file SHA-256 and
  normalized modes.

Every pack consumer reads only the snapshot; the snapshot owns its temp directory
and removes it on normal return and on errors.

Traversal is descriptor-anchored where the platform supports directory file
descriptors (Linux/macOS): the root is opened no-follow, every child is opened
relative to its parent descriptor, and an untrusted child is never re-resolved
from a mutable absolute path. On platforms without ``dir_fd`` support (Windows) a
conservative path-based fallback re-lstats and compares identity before reading
and rejects symlink/reparse substitutions; its residual limitation is that it
cannot fully close the descriptor-anchoring window, so it fails closed on any
detected identity change rather than claiming an identical guarantee.

This removes mutable-source time-of-check/time-of-use from Arena's OWN pack
consumers. It does not isolate the reviewer process, and an internally consistent
snapshot does not make a self-reported run official. Patch semantics remain Phase
1D. No filesystem API can prevent a source from changing after a command returns;
changes are detected through the operation's completion boundary and fail closed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from arena.benchmark.pack_hash import pack_checksum, stored_checksum
from arena.core import limits
from arena.core.errors import SnapshotError

_READ_CHUNK = 65536
SNAPSHOT_MANIFEST_VERSION = 1

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_BINARY = getattr(os, "O_BINARY", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_DIR_FLAGS = os.O_RDONLY | _NOFOLLOW | _DIRECTORY
_FILE_FLAGS = os.O_RDONLY | _NOFOLLOW | _BINARY

# Descriptor-anchored traversal needs scandir(fd), open(..., dir_fd=...) and
# stat(..., dir_fd=...). Where unavailable (Windows), fall back to the path walk.
_DIR_FD = (
    bool(_DIRECTORY)
    and os.scandir in getattr(os, "supports_fd", set())
    and os.open in os.supports_dir_fd
)
# chmod sets exact POSIX permission bits only on POSIX; on Windows it cannot, so the
# exact intended-mode check is POSIX-only and modes are sealed as read-back values.
_POSIX = os.name == "posix"


@dataclass(frozen=True)
class SnapshotManifestEntry:
    """One regular file or directory in the sealed snapshot."""

    kind: str  # "file" | "dir"
    path: str  # relative POSIX path ("" is the snapshot root directory)
    size: int  # 0 for directories
    sha256: str  # "" for directories
    mode: int  # normalized execution-relevant bits (files 0o755/0o644, dirs 0o755)


def manifest_digest(entries: tuple[SnapshotManifestEntry, ...]) -> str:
    """Deterministic SHA-256 over the complete (sorted) snapshot manifest."""
    digest = hashlib.sha256()
    digest.update(f"v{SNAPSHOT_MANIFEST_VERSION}\0".encode())
    for entry in sorted(entries, key=lambda e: (e.path, e.kind)):
        digest.update(
            f"{entry.kind}\0{entry.path}\0{entry.size}\0{entry.sha256}\0{entry.mode}\0".encode()
        )
    return digest.hexdigest()


# Per-entry identity used to detect a change between discovery and use, and to
# compare the source tree before and after copying.
_Identity = tuple[int, int, int, int, int, int]


def _identity(info: os.stat_result) -> _Identity:
    return (
        stat.S_IFMT(info.st_mode),
        info.st_dev,
        info.st_ino,
        info.st_size,
        int(info.st_mtime_ns),
        getattr(info, "st_nlink", 0),
    )


@dataclass
class _WalkState:
    entry_count: int = 0
    file_count: int = 0
    dir_count: int = 0
    total_bytes: int = 0
    normalized: dict[str, str] = field(default_factory=dict)


def _normalized_key(relative: str) -> str:
    """Case-folded NFC key; collapses NFC, case-fold, and case-fold+NFC collisions."""
    return unicodedata.normalize("NFC", relative).casefold()


def _check_name(name: str) -> None:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SnapshotError(
            "unsupported_filename", "pack contains an undecodable filename"
        ) from exc


def _register(state: _WalkState, relative: str) -> None:
    key = _normalized_key(relative)
    existing = state.normalized.get(key)
    if existing is not None and existing != relative:
        raise SnapshotError(
            "path_collision",
            f"pack entries collide under Unicode/case normalization: {existing!r} and {relative!r}",
        )
    state.normalized[key] = relative


def _mode_for(info: os.stat_result, *, is_dir: bool) -> int:
    if is_dir:
        return 0o755
    return 0o755 if info.st_mode & stat.S_IXUSR else 0o644


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte, treating zero progress as a failure."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise SnapshotError("destination_write_failed", "zero-progress write to the snapshot")
        view = view[written:]


def _hash_fd(fd: int, *, limit: int) -> tuple[int, str]:
    """Hash an open descriptor in bounded chunks; return (size, hexdigest)."""
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = os.read(fd, _READ_CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise SnapshotError("total_bytes_exceeded", "snapshot file exceeds the per-file limit")
        digest.update(chunk)
    return size, digest.hexdigest()


# A file opener returns (fd, lstat_used_for_open) so callers can compare the opened
# descriptor against what was discovered before reading any bytes.
_Opener = Callable[[], int]


def _copy_one_file(
    relative: str,
    opener: _Opener,
    info: os.stat_result,
    dst: Path,
    state: _WalkState,
    inodes: set[tuple[int, int]],
) -> SnapshotManifestEntry:
    if info.st_dev and info.st_ino:
        identity = (info.st_dev, info.st_ino)
        if identity in inodes:
            raise SnapshotError("hardlink_found", f"pack file is a hardlink alias: {relative!r}")
        inodes.add(identity)
    fd = opener()
    try:
        before = os.fstat(fd)
        # Identity-before-read: the opened descriptor must be the regular file we
        # discovered, with the same identity/size/mtime, before any byte is read.
        if not stat.S_ISREG(before.st_mode):
            raise SnapshotError(
                "unsafe_file_type", f"pack entry is not a regular file: {relative!r}"
            )
        if _identity(before) != _identity(info):
            raise SnapshotError(
                "file_changed_during_copy", f"pack file changed before reading: {relative!r}"
            )
        out_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY
        out = os.open(dst, out_flags, 0o600)
        digest = hashlib.sha256()
        size = 0
        try:
            while True:
                chunk = os.read(fd, _READ_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limits.PACK_FILE_BYTES:
                    raise SnapshotError(
                        "total_bytes_exceeded",
                        f"pack file exceeds the per-file limit: {relative!r}",
                    )
                state.total_bytes += len(chunk)
                if state.total_bytes > limits.SNAPSHOT_MAX_TOTAL_BYTES:
                    raise SnapshotError("total_bytes_exceeded", "pack exceeds the total byte limit")
                digest.update(chunk)
                _write_all(out, chunk)
            os.fsync(out)
        except BaseException:
            os.close(out)
            _safe_unlink(dst)
            raise
        os.close(out)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    # Post-read: the source descriptor must not have changed while being read.
    if _identity(before) != _identity(after) or before.st_size != size:
        _safe_unlink(dst)
        raise SnapshotError(
            "file_changed_during_copy", f"pack file changed while copying: {relative!r}"
        )
    intended = _mode_for(before, is_dir=False)
    os.chmod(dst, intended)
    actual = dst.lstat().st_mode & 0o777
    _verify_destination(dst, size, digest.hexdigest(), intended, relative)
    # Seal the mode the filesystem actually stored: POSIX keeps the intended bits,
    # while Windows ignores them (so this is the read-back value). The seal and the
    # verify() rebuild both read this same value, so a later chmod is still detected.
    return SnapshotManifestEntry(
        kind="file", path=relative, size=size, sha256=digest.hexdigest(), mode=actual
    )


def _safe_unlink(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _verify_destination(dst: Path, size: int, sha: str, mode: int, relative: str) -> None:
    """The copied file must be a regular file of the exact size, bytes and (POSIX) mode."""
    dinfo = dst.lstat()
    # The exact intended-mode check applies only where chmod sets POSIX bits exactly;
    # on Windows chmod cannot, so the mode is verified via the full seal instead.
    bad_mode = _POSIX and (dinfo.st_mode & 0o777) != mode
    if not stat.S_ISREG(dinfo.st_mode) or dinfo.st_size != size or bad_mode:
        _safe_unlink(dst)
        raise SnapshotError(
            "destination_verification_failed", f"snapshot copy is wrong: {relative!r}"
        )
    fd = os.open(dst, _FILE_FLAGS)
    try:
        read_size, read_sha = _hash_fd(fd, limit=limits.PACK_FILE_BYTES)
    finally:
        os.close(fd)
    if read_size != size or read_sha != sha:
        _safe_unlink(dst)
        raise SnapshotError(
            "destination_verification_failed", f"snapshot copy mismatch: {relative!r}"
        )


# --------------------------------------------------------------------------- #
# Secure walk (descriptor-anchored, with a path-based fallback)               #
# --------------------------------------------------------------------------- #

_VisitFile = Callable[[str, _Opener, os.stat_result], SnapshotManifestEntry | None]
_VisitDir = Callable[[str, os.stat_result], SnapshotManifestEntry | None]


def _classify(state: _WalkState, name: str, info: os.stat_result, relative: str) -> str:
    _check_name(name)
    if stat.S_ISLNK(info.st_mode):
        raise SnapshotError("symlink_found", f"pack contains a symlink: {relative!r}")
    if stat.S_ISDIR(info.st_mode):
        state.dir_count += 1
        if state.dir_count > limits.SNAPSHOT_MAX_DIRS:
            raise SnapshotError("directory_count_exceeded", "pack exceeds the directory limit")
        return "dir"
    if stat.S_ISREG(info.st_mode):
        state.file_count += 1
        if state.file_count > limits.SNAPSHOT_MAX_FILES:
            raise SnapshotError("file_count_exceeded", "pack exceeds the file limit")
        return "file"
    raise SnapshotError(
        "unsafe_file_type", f"pack contains an unsupported special file: {relative!r}"
    )


def _enumerate(
    entries_iter: Iterator, state: _WalkState, prefix: str
) -> list[tuple[str, os.stat_result, str]]:
    """Bounded enumeration: enforce the entry cap WHILE iterating, then sort."""
    collected: list[tuple[str, os.stat_result, str]] = []
    for entry in entries_iter:
        state.entry_count += 1
        if state.entry_count > limits.SNAPSHOT_MAX_ENTRIES:
            raise SnapshotError("entry_count_exceeded", "pack exceeds the total entry limit")
        info = entry.stat(follow_symlinks=False)
        relative = f"{prefix}{entry.name}"
        kind = _classify(state, entry.name, info, relative)
        collected.append((entry.name, info, kind))
    collected.sort(key=lambda item: item[0])
    return collected


def _walk_fd(
    parent_fd: int,
    prefix: str,
    depth: int,
    state: _WalkState,
    visit_file: _VisitFile,
    visit_dir: _VisitDir,
) -> Iterator[SnapshotManifestEntry]:
    if depth > limits.SNAPSHOT_MAX_DEPTH:
        raise SnapshotError("path_too_deep", "pack path depth exceeds the limit")
    with os.scandir(parent_fd) as iterator:
        children = _enumerate(iterator, state, prefix)
    for name, info, kind in children:
        relative = f"{prefix}{name}"
        _register(state, relative)
        if kind == "dir":
            entry = visit_dir(relative, info)
            if entry is not None:
                yield entry
            child_fd = os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
            try:
                opened = os.fstat(child_fd)
                if not stat.S_ISDIR(opened.st_mode) or _identity(opened) != _identity(info):
                    raise SnapshotError(
                        "tree_changed_during_copy",
                        f"directory changed during traversal: {relative!r}",
                    )
                yield from _walk_fd(
                    child_fd, f"{relative}/", depth + 1, state, visit_file, visit_dir
                )
            finally:
                os.close(child_fd)
        else:

            def opener(_name: str = name, _fd: int = parent_fd) -> int:
                return os.open(_name, _FILE_FLAGS, dir_fd=_fd)

            entry = visit_file(relative, opener, info)
            if entry is not None:
                yield entry


def _walk_path(
    directory: Path,
    prefix: str,
    depth: int,
    state: _WalkState,
    visit_file: _VisitFile,
    visit_dir: _VisitDir,
) -> Iterator[SnapshotManifestEntry]:
    if depth > limits.SNAPSHOT_MAX_DEPTH:
        raise SnapshotError("path_too_deep", "pack path depth exceeds the limit")
    with os.scandir(directory) as iterator:
        children = _enumerate(iterator, state, prefix)
    for name, _scandir_info, kind in children:
        relative = f"{prefix}{name}"
        _register(state, relative)
        child = directory / name
        # Re-lstat with a fresh stat for the canonical identity: os.scandir's cached
        # DirEntry.stat() sets st_ino/st_dev/st_nlink to 0 on Windows, so comparing it
        # against a later lstat/fstat would spuriously flag an unchanged entry. A fresh
        # lstat is consistent with the fstat/lstat used in every later comparison.
        try:
            info = child.lstat()
        except FileNotFoundError as exc:
            raise SnapshotError(
                "tree_changed_during_copy", f"entry disappeared during traversal: {relative!r}"
            ) from exc
        if stat.S_ISLNK(info.st_mode):
            raise SnapshotError("symlink_found", f"pack contains a symlink: {relative!r}")
        if kind == "dir":
            if not stat.S_ISDIR(info.st_mode):
                raise SnapshotError(
                    "tree_changed_during_copy", f"directory replaced during traversal: {relative!r}"
                )
            entry = visit_dir(relative, info)
            if entry is not None:
                yield entry
            rechecked = child.lstat()
            if stat.S_ISLNK(rechecked.st_mode) or not stat.S_ISDIR(rechecked.st_mode):
                raise SnapshotError(
                    "symlink_found", f"directory replaced during traversal: {relative!r}"
                )
            if _identity(rechecked) != _identity(info):
                raise SnapshotError(
                    "tree_changed_during_copy", f"directory changed during traversal: {relative!r}"
                )
            yield from _walk_path(child, f"{relative}/", depth + 1, state, visit_file, visit_dir)
        else:
            if not stat.S_ISREG(info.st_mode):
                raise SnapshotError(
                    "unsafe_file_type", f"pack entry is not a regular file: {relative!r}"
                )

            def opener(
                _path: Path = child, _info: os.stat_result = info, _rel: str = relative
            ) -> int:
                fd = os.open(_path, _FILE_FLAGS)
                if _identity(os.fstat(fd)) != _identity(_info):
                    os.close(fd)
                    raise SnapshotError(
                        "file_changed_during_copy",
                        f"pack file changed before reading: {_rel!r}",
                    )
                return fd

            entry = visit_file(relative, opener, info)
            if entry is not None:
                yield entry


def _secure_walk(
    root: Path,
    root_info: os.stat_result,
    state: _WalkState,
    visit_file: _VisitFile,
    visit_dir: _VisitDir,
) -> Iterator[SnapshotManifestEntry]:
    if _DIR_FD:
        root_fd = os.open(root, _DIR_FLAGS)
        try:
            opened = os.fstat(root_fd)
            if not stat.S_ISDIR(opened.st_mode) or _identity(opened) != _identity(root_info):
                raise SnapshotError(
                    "tree_changed_during_copy", "pack root changed during traversal"
                )
            yield from _walk_fd(root_fd, "", 1, state, visit_file, visit_dir)
        finally:
            os.close(root_fd)
    else:
        yield from _walk_path(root, "", 1, state, visit_file, visit_dir)


# --------------------------------------------------------------------------- #
# Source identity map and copy                                                #
# --------------------------------------------------------------------------- #


def _source_identity(root: Path, root_info: os.stat_result) -> dict[str, _Identity]:
    """Securely walk the source read-only and map every entry to its identity."""
    identity: dict[str, _Identity] = {"": _identity(root_info)}
    state = _WalkState()

    def on_file(relative: str, opener: _Opener, info: os.stat_result) -> None:
        identity[relative] = _identity(info)
        return None

    def on_dir(relative: str, info: os.stat_result) -> None:
        identity[relative] = _identity(info)
        return None

    for _ in _secure_walk(root, root_info, state, on_file, on_dir):
        pass
    return identity


def _copy_tree(
    source: Path, dst_root: Path, root_info: os.stat_result
) -> tuple[list[SnapshotManifestEntry], _WalkState]:
    """Securely copy ``source`` into ``dst_root`` and return the manifest + counters."""
    manifest: list[SnapshotManifestEntry] = []
    inodes: set[tuple[int, int]] = set()
    state = _WalkState()
    manifest.append(SnapshotManifestEntry(kind="dir", path="", size=0, sha256="", mode=0o755))

    def on_dir(relative: str, info: os.stat_result) -> SnapshotManifestEntry:
        target = dst_root / relative
        os.mkdir(target, 0o700)
        os.chmod(target, 0o755)
        actual = target.lstat().st_mode & 0o777
        return SnapshotManifestEntry(kind="dir", path=relative, size=0, sha256="", mode=actual)

    def on_file(relative: str, opener: _Opener, info: os.stat_result) -> SnapshotManifestEntry:
        return _copy_one_file(relative, opener, info, dst_root / relative, state, inodes)

    manifest.extend(_secure_walk(source, root_info, state, on_file, on_dir))
    return manifest, state


def _scan_snapshot_manifest(root: Path) -> list[SnapshotManifestEntry]:
    """Securely rebuild the full manifest from a sealed snapshot tree (for verify)."""
    root_info = root.lstat()
    manifest: list[SnapshotManifestEntry] = [
        SnapshotManifestEntry(kind="dir", path="", size=0, sha256="", mode=0o755)
    ]
    state = _WalkState()

    def on_dir(relative: str, info: os.stat_result) -> SnapshotManifestEntry:
        return SnapshotManifestEntry(
            kind="dir", path=relative, size=0, sha256="", mode=info.st_mode & 0o777
        )

    def on_file(relative: str, opener: _Opener, info: os.stat_result) -> SnapshotManifestEntry:
        fd = opener()
        try:
            size, sha = _hash_fd(fd, limit=limits.PACK_FILE_BYTES)
        finally:
            os.close(fd)
        return SnapshotManifestEntry(
            kind="file", path=relative, size=size, sha256=sha, mode=info.st_mode & 0o777
        )

    manifest.extend(_secure_walk(root, root_info, state, on_file, on_dir))
    return manifest


# --------------------------------------------------------------------------- #
# Public snapshot API                                                         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PackSnapshot:
    """A sealed, verified, immutable copy of a source pack. Reads target the snapshot."""

    source: Path
    root: Path
    checksum: str  # public pack content checksum
    manifest_digest: str  # full-seal digest over the complete manifest
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
        """Rebuild the full snapshot manifest and reject ANY post-seal drift.

        Detects added/removed/modified regular files (including the root pack.sha256),
        added/removed empty directories, mode changes, and introduced symlinks or
        special entries. The public pack checksum is also recomputed; it is only one
        component, not the whole seal.
        """
        try:
            rebuilt = tuple(_scan_snapshot_manifest(self.root))
        except SnapshotError as exc:
            raise SnapshotError(
                "snapshot_changed_after_sealing", "the snapshot tree changed"
            ) from exc
        if manifest_digest(rebuilt) != self.manifest_digest:
            raise SnapshotError("snapshot_changed_after_sealing", "the snapshot manifest changed")
        if pack_checksum(self.root) != self.checksum:
            raise SnapshotError("snapshot_changed_after_sealing", "the snapshot content changed")


def _assert_source_unchanged(source: Path, before: dict[str, _Identity]) -> None:
    """Re-scan the source and require the COMPLETE tree (files and dirs) to match."""
    try:
        root_info = source.lstat()
    except FileNotFoundError as exc:
        raise SnapshotError("tree_changed_during_copy", "the pack source disappeared") from exc
    if stat.S_ISLNK(root_info.st_mode) or not stat.S_ISDIR(root_info.st_mode):
        raise SnapshotError("tree_changed_during_copy", "the pack root changed during copy")
    after = _source_identity(source, root_info)
    if after != before:
        raise SnapshotError("tree_changed_during_copy", "the pack tree changed during copy")


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

    # Capture the complete source identity first, copy, then require an exact match.
    identity_before = _source_identity(source, root_info)

    temp_root = Path(tempfile.mkdtemp(prefix="arena-snapshot-"))
    try:
        snapshot_root = temp_root / "pack"
        os.mkdir(snapshot_root, 0o755)
        manifest_list, state = _copy_tree(source, snapshot_root, root_info)
        _assert_source_unchanged(source, identity_before)
        if len(manifest_list) > limits.SNAPSHOT_MANIFEST_ENTRIES:
            raise SnapshotError("file_count_exceeded", "pack exceeds the snapshot manifest limit")
        manifest = tuple(manifest_list)
        snapshot = PackSnapshot(
            source=source,
            root=snapshot_root,
            checksum=pack_checksum(snapshot_root),
            manifest_digest=manifest_digest(manifest),
            stored_checksum=stored_checksum(snapshot_root),
            manifest=manifest,
            file_count=state.file_count,
            dir_count=state.dir_count,
            total_bytes=state.total_bytes,
        )
        yield snapshot
        # Belt-and-suspenders: re-verify the full seal on normal exit (consumers also
        # verify before sealing their own evidence).
        snapshot.verify()
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
