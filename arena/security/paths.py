"""Path-containment guards for adversarial pack content.

A case id and the path fields in a pack's manifest and case files are
attacker-controlled: the threat model treats benchmark packs as adversarial, yet
those strings become physical path components (``benchmark_dir / case_id``,
``case_dir / after_dir``) and, in the patch applier, an ``rmtree`` target. These
helpers reject anything that could escape its declared root before it reaches the
filesystem, and refuse a delete that is not strictly inside its workspace root.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from arena.core.errors import ValidationError

# A case id is used verbatim as a directory name, so it must be a slug: it may
# not contain path separators, traversal, drive letters, or NUL. The first
# character is alphanumeric, which also rules out a component equal to "..".
_CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def validate_case_id(value: str) -> str:
    """Return value if it is a safe slug, else raise ValidationError."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValidationError(f"unsafe case id {value!r}: empty or contains NUL")
    if not _CASE_ID_RE.match(value):
        raise ValidationError(
            f"unsafe case id {value!r}: expected a slug "
            "[A-Za-z0-9][A-Za-z0-9_.-]{0,127} with no separators, traversal, "
            "or drive letters"
        )
    return value


def validate_relative_path(value: str) -> str:
    """Return value if it is a safe pack-relative path, else raise.

    Rejects empty strings, NUL, backslashes, absolute paths, drive letters, and
    any ".." component. Containment against an actual root (including symlink
    escapes) is enforced by resolve_under.
    """
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValidationError(f"unsafe path {value!r}: empty or contains NUL")
    if "\\" in value:
        raise ValidationError(f"unsafe path {value!r}: backslash separators are not allowed")
    if ":" in value:
        raise ValidationError(f"unsafe path {value!r}: ':' (drive letter) is not allowed")
    pure = PurePosixPath(value)
    if pure.is_absolute():
        raise ValidationError(f"unsafe path {value!r}: must be relative, not absolute")
    if any(part == ".." for part in pure.parts):
        raise ValidationError(f"unsafe path {value!r}: '..' traversal is not allowed")
    return value


def resolve_under(root: Path, relative: str) -> Path:
    """Resolve relative under root and assert the result stays inside root.

    ``.resolve()`` collapses symlinks, so a path that traverses a symlink out of
    root is rejected too.
    """
    validate_relative_path(relative)
    root_resolved = root.resolve()
    target = (root_resolved / relative).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValidationError(f"path {relative!r} escapes its root {root}")
    return target


def assert_safe_delete_target(root: Path, target: Path) -> None:
    """Refuse to delete the root itself or anything outside it.

    Both paths are resolved first, so a symlinked target that points outside
    root is rejected before any rmtree runs.
    """
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    if target_resolved == root_resolved:
        raise ValidationError(f"refusing to delete the root itself: {root}")
    if root_resolved not in target_resolved.parents:
        raise ValidationError(f"refusing to delete {target}: outside {root}")
