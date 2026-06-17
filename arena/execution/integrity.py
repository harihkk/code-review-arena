"""Detect candidate tampering with hidden tests and oracle data.

Blocking a patch from *declaring* test paths is not enough: patched runtime code
can still rewrite, delete, or replace test files while the suite runs. We take a
content hash of the test/oracle tree before and after execution and treat any
change -- including a newly introduced symlink or special file -- as a tampering
violation that invalidates the result.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Caches and bytecode are execution byproducts, not part of the test contract.
_IGNORED_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _relposix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_manifest(root: Path) -> dict[str, str]:
    """Map each regular file under ``root`` to its sha256, by relative POSIX path.

    Symlinks and other special files are recorded with a sentinel value rather
    than hashed: their mere presence is a finding, and following them would be an
    escape vector.
    """
    manifest: dict[str, str] = {}
    if not root.is_dir():
        return manifest
    for path in sorted(root.rglob("*")):
        if any(part in _IGNORED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            manifest[_relposix(path, root)] = "symlink"
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            manifest[_relposix(path, root)] = "special"
            continue
        if path.suffix == ".pyc":
            continue
        manifest[_relposix(path, root)] = _sha256(path)
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
