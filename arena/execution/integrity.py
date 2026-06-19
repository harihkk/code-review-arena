"""Detect candidate tampering with hidden tests and oracle data.

Blocking a patch from *declaring* test paths is not enough: patched runtime code
can still rewrite, delete, or replace test files while the suite runs. We take a
content hash of the test/oracle tree before and after execution and treat any
change -- including a newly introduced symlink or special file -- as a tampering
violation that invalidates the result.

The tree is always walked with ``os.walk(..., followlinks=False)`` so a symlink
never lures the walk out of the tree (host-data exfiltration) or into a loop.
Cache directories are byproducts of test execution: they may be excluded from the
post-execution comparison (file_manifest), but never from admission
(find_unsafe_files), which rejects every symlink and special file anywhere,
including ones named like a cache.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

# Caches and bytecode are execution byproducts, not part of the test contract.
# They are skipped only by the post-execution comparison, never by admission.
_IGNORED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _relposix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _classify(path: Path) -> str | None:
    """Return 'symlink'/'special' for an unsafe entry, None for a regular file."""
    if path.is_symlink():
        return "symlink"
    if not path.is_file():
        return "special"  # FIFO, socket, device, or other non-regular file
    return None


def file_manifest(root: Path) -> dict[str, str]:
    """Map each regular file under ``root`` to its sha256, by relative POSIX path.

    Symlinks and other special files are recorded with a sentinel value rather
    than hashed: their mere presence is a finding, and following them would be an
    escape vector. Cache directories are pruned (they are execution byproducts),
    and the walk never follows symlinks.
    """
    manifest: dict[str, str] = {}
    if not root.is_dir():
        return manifest
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in list(dirnames):
            entry = base / name
            if name in _IGNORED_DIR_NAMES:
                dirnames.remove(name)  # byproduct: do not descend or record contents
                continue
            if entry.is_symlink():  # a real subdir is fine; only a symlinked dir is unsafe
                manifest[_relposix(entry, root)] = "symlink"
                dirnames.remove(name)  # do not descend a symlinked dir
        for name in filenames:
            entry = base / name
            kind = _classify(entry)
            if kind is not None:
                manifest[_relposix(entry, root)] = kind
            elif entry.suffix != ".pyc":
                manifest[_relposix(entry, root)] = _sha256(entry)
    return manifest


def manifest_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Describe how ``after`` differs from ``before`` as sorted change tokens."""
    changes: list[str] = []
    for key in sorted(set(before) | set(after)):
        previous = before.get(key)
        current = after.get(key)
        if previous is None:
            changes.append(f"created:{key}")
        elif current is None:
            changes.append(f"deleted:{key}")
        elif previous != current:
            changes.append(f"modified:{key}")
    return changes


def unsafe_entries(manifest: dict[str, str]) -> list[str]:
    """Relative paths in ``manifest`` that are symlinks or special files."""
    return sorted(key for key, value in manifest.items() if value in {"symlink", "special"})


def find_unsafe_files(root: Path) -> list[str]:
    """Symlinks and special files (sockets/devices/FIFOs) anywhere under ``root``.

    A pack must contain only regular files and directories: a symlink would be
    followed when the case is copied into a workspace, letting an untrusted pack
    read or write outside its tree. Admission rejects every symlink and special
    file at any depth, INCLUDING under cache-named directories -- a symlink named
    ``.pytest_cache`` pointing outside the tree must not slip through. The walk
    never follows symlinks, so it cannot be lured out of the tree or into a loop.
    """
    unsafe: list[str] = []
    if not root.is_dir():
        return unsafe
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        for name in list(dirnames):
            entry = base / name
            if entry.is_symlink():  # a real subdir is fine; only a symlinked dir is unsafe
                unsafe.append(_relposix(entry, root))
                dirnames.remove(name)  # flag it, never descend a symlinked dir
        for name in filenames:
            entry = base / name
            if _classify(entry) is not None:
                unsafe.append(_relposix(entry, root))
    return sorted(unsafe)
