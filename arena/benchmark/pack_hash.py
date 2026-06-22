"""Content checksums for benchmark packs.

A pack checksum pins the exact bytes of every regular file in the pack, so a pack
inspected once can be verified again at run time: results from a silently modified
pack are flagged instead of trusted. Every regular file is covered except the root
``pack.sha256`` artifact itself (which necessarily cannot contain its own digest).
Hidden files and bytecode caches are covered too -- as of Phase 1C the checksum is
computed from an immutable snapshot whose secure traversal copies every regular
file, so nothing pack-controlled is outside the digest.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from arena.core.bounded_io import read_bytes_bounded, read_text_bounded
from arena.core.limits import CHECKSUM_FILE_BYTES, PACK_FILE_BYTES

PACK_CHECKSUM_FILENAME = "pack.sha256"


def _content_files(benchmark_dir: Path) -> list[Path]:
    files = []
    for path in sorted(benchmark_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(benchmark_dir)
        if relative == Path(PACK_CHECKSUM_FILENAME):  # only the root checksum artifact
            continue
        files.append(path)
    return files


def pack_checksum(benchmark_dir: Path) -> str:
    """SHA-256 over sorted relative paths and file bytes of the pack.

    Framing per file: sorted relative POSIX path, NUL, exact bytes, NUL. Phase 1C
    computes this from snapshot bytes; the algorithm is unchanged.
    """
    digest = hashlib.sha256()
    for path in _content_files(benchmark_dir):
        digest.update(path.relative_to(benchmark_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(read_bytes_bounded(path, PACK_FILE_BYTES, label="pack file"))
        digest.update(b"\0")
    return digest.hexdigest()


def stored_checksum(benchmark_dir: Path) -> str | None:
    path = benchmark_dir / PACK_CHECKSUM_FILENAME
    if not path.is_file():
        return None
    return (
        read_text_bounded(path, CHECKSUM_FILE_BYTES, label=PACK_CHECKSUM_FILENAME).strip() or None
    )


def _nonchecksum_manifest(snapshot: object) -> tuple:
    """The full snapshot manifest minus the root pack.sha256 file entry.

    Two snapshots of a source that changed only in pack.sha256 produce identical
    values, so this proves no other source entry moved across the write.
    """
    return tuple(
        (e.kind, e.path, e.size, e.sha256, e.mode)
        for e in snapshot.manifest  # type: ignore[attr-defined]
        if not (e.kind == "file" and e.path == PACK_CHECKSUM_FILENAME)
    )


def _atomic_write(target: Path, data: bytes) -> None:
    """Exclusive-create temp + complete write + fsync + atomic replace of ``target``."""
    fd, tmp = tempfile.mkstemp(prefix=".pack-sha256-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_checksum(benchmark_dir: Path) -> str:
    """Write pack.sha256, verified through secure snapshots only (no live-tree read).

    Snapshots the source to compute the intended public checksum, atomically writes
    the root artifact, then re-snapshots and verifies that the public checksum and
    stored checksum equal the intended value and that no non-checksum source entry
    moved. On any mismatch it restores the prior artifact (or removes a newly created
    one) and raises, so a known-stale checksum is never left behind.

    No filesystem API can prevent the source from changing AFTER this returns; the
    guarantee is that the artifact written here was verified against the source state
    through the completion of this operation.
    """
    from arena.benchmark.snapshot import snapshot_pack
    from arena.core.errors import SnapshotError

    target = benchmark_dir / PACK_CHECKSUM_FILENAME
    with snapshot_pack(benchmark_dir) as snapshot:
        intended = snapshot.checksum
        before_nonchecksum = _nonchecksum_manifest(snapshot)

    had_prior = target.is_file()
    prior = (
        read_bytes_bounded(target, CHECKSUM_FILE_BYTES, label=PACK_CHECKSUM_FILENAME)
        if had_prior
        else None
    )

    _atomic_write(target, f"{intended}\n".encode())
    try:
        with snapshot_pack(benchmark_dir) as after:
            if (
                after.checksum != intended
                or (after.stored_checksum or "") != intended
                or _nonchecksum_manifest(after) != before_nonchecksum
            ):
                raise SnapshotError(
                    "source_changed_before_checksum_write",
                    "pack source changed across the checksum write",
                )
    except SnapshotError:
        if had_prior and prior is not None:
            _atomic_write(target, prior)
        else:
            try:
                os.unlink(target)
            except OSError:
                pass
        raise
    return intended
