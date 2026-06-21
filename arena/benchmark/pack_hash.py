"""Content checksums for benchmark packs.

A pack checksum pins the exact bytes of every case file, so a pack inspected
once can be verified again at run time: results from a silently modified pack
are flagged instead of trusted. Hidden files and bytecode caches are excluded
so OS noise (.DS_Store) does not churn the checksum.
"""

from __future__ import annotations

import hashlib
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
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        files.append(path)
    return files


def unhashable_content(benchmark_dir: Path) -> list[str]:
    """Regular files present in the pack but EXCLUDED from pack_checksum.

    These sit under a dot-prefixed component or ``__pycache__``, so the digest
    cannot see them and a pack could be modified there without changing its
    checksum. Admission must reject such content until snapshot hashing (Phase 1C)
    covers every regular file; only ``pack.sha256`` (which necessarily contains
    its own digest) is legitimately excluded.
    """
    omitted: list[str] = []
    for path in sorted(benchmark_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(benchmark_dir)
        if relative == Path(PACK_CHECKSUM_FILENAME):  # only the root checksum artifact
            continue
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            omitted.append(relative.as_posix())
    return omitted


def pack_checksum(benchmark_dir: Path) -> str:
    """SHA-256 over sorted relative paths and file bytes of the pack."""
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
    checksum = pack_checksum(benchmark_dir)
    (benchmark_dir / PACK_CHECKSUM_FILENAME).write_text(checksum + "\n", encoding="utf-8")
    return checksum
