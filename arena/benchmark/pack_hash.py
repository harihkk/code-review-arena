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


def write_checksum(benchmark_dir: Path) -> str:
    """Compute the checksum from a snapshot, then write the root artifact atomically.

    The digest is computed from a sealed snapshot; before writing, the source is
    re-checked so a digest representing stale source bytes is never written.
    """
    # Lazy import: snapshot imports pack_hash, so importing it at module load would
    # create a cycle.
    from arena.benchmark.snapshot import snapshot_pack
    from arena.core.errors import SnapshotError

    with snapshot_pack(benchmark_dir) as snapshot:
        checksum = snapshot.checksum
        if pack_checksum(benchmark_dir) != checksum:
            raise SnapshotError(
                "source_changed_before_checksum_write",
                "pack source changed between snapshot and checksum write",
            )
    target = benchmark_dir / PACK_CHECKSUM_FILENAME
    tmp = benchmark_dir / f"{PACK_CHECKSUM_FILENAME}.tmp"
    tmp.write_text(checksum + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return checksum
