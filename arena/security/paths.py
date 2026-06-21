"""Path-containment guards for adversarial pack content.

A case id and the path fields in a pack's manifest and case files are
attacker-controlled: the threat model treats benchmark packs as adversarial, yet
those strings become physical path components (``benchmark_dir / case_id``,
``case_dir / after_dir``) and, in the patch applier, an ``rmtree`` target.

Two layers are provided:

- Pydantic-facing types (``SafeRelativePath``, ``SafeCaseId``) whose validators
  raise ``ValueError`` so a bad value is collected as a normal Pydantic error with
  an accurate field location (for example ``input.after_dir``).
- Domain wrappers (``validate_relative_path``, ``validate_case_id``) that raise
  Arena's ``ValidationError`` for callers at filesystem/I/O boundaries.

Path policy is a deliberately strict, portable ASCII profile: only ASCII letters,
digits, ``_``, ``-``, ``.`` and ``/``. We do not support Unicode filenames in pack
paths (no concrete need), which removes whole classes of confusable and
normalization attacks rather than blacklisting examples. Case-insensitive and
Unicode-normalization collisions are enforced again at snapshot construction
(Phase 1C). If Unicode paths ever become a requirement, the exact normalization
and confusable profile must be defined before relaxing this.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator

from arena.core.errors import ValidationError

# A case id is one path component: a slug, never a relative path.
# Portable ASCII profile: a single path component may contain only these
# characters (no separator). Both a relative path (split on "/") and a case id
# (which is exactly one component, so it becomes a directory name) are checked
# through the SAME component validator, so their filesystem rules cannot drift.
_ALLOWED_COMPONENT_CHARS = re.compile(r"\A[A-Za-z0-9_.-]+\Z")
_MAX_PATH_LENGTH = 1024
_MAX_COMPONENT_LENGTH = 255
# A case id becomes a directory name, so it is the strictest: a single component
# that begins with an ASCII alphanumeric (no leading '.', '_' or '-', which would
# read as a hidden or option-like directory), bounded to this length.
_MAX_CASE_ID_LENGTH = 128
# Windows reserved device names (case-insensitive), reserved even with an
# extension such as NUL.txt; the stem before the first dot is what matters.
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _component_error(component: object) -> str | None:
    """Return why a single path component is unsafe, or None. Shared by paths and ids."""
    if not isinstance(component, str) or not component:
        return "empty component"
    if len(component) > _MAX_COMPONENT_LENGTH:
        return f"component longer than {_MAX_COMPONENT_LENGTH} characters"
    if component in {".", ".."}:
        return "'.' and '..' are not valid components"
    # A dot-prefixed component is excluded by the current pack checksum, so content
    # under it would not be covered by the pack digest. Reject it until snapshot
    # hashing (Phase 1C) covers every regular file.
    if component.startswith("."):
        return "a component may not start with a dot (it is omitted from the pack checksum)"
    if not _ALLOWED_COMPONENT_CHARS.match(component):
        return "only ASCII letters, digits, '_', '-', and '.' are allowed"
    if component.endswith(".") or component.endswith(" "):
        return "a component may not end with a dot or space"
    if component.split(".")[0].upper() in _WINDOWS_RESERVED:
        return f"'{component}' uses a reserved device name"
    return None


def _relative_path_error(value: object) -> str | None:
    """Return why ``value`` is not a safe portable relative path, or None if it is."""
    if not isinstance(value, str) or not value:
        return "empty path"
    if len(value) > _MAX_PATH_LENGTH:
        return f"path longer than {_MAX_PATH_LENGTH} characters"
    if value.startswith("/") or value.endswith("/"):
        return "leading or trailing '/' is not allowed"
    for component in value.split("/"):
        error = _component_error(component)
        if error is not None:
            return error
    return None


def _check_relative_path(value: str) -> str:
    """Pydantic-facing validator: raises ValueError so Pydantic records the error."""
    error = _relative_path_error(value)
    if error is not None:
        raise ValueError(f"unsafe path {value!r}: {error}")
    return value


SafeRelativePath = Annotated[str, AfterValidator(_check_relative_path)]


def admit_reviewer_path(value: object) -> str:
    """Admit a reviewer-supplied finding path to a canonical pack-relative path.

    ``Finding.file`` is reviewer-controlled. Reviewers conventionally prefix paths
    with a diff-style ``a/`` or ``b/`` or a leading ``./``; exactly one such
    presentation prefix is removed, then the remainder must satisfy the SAME
    portable relative-path policy as pack paths (ASCII profile, no traversal, no
    absolute/UNC/drive/backslash/control/dot-prefixed components). Returns the
    canonical pack-relative path, or raises ``ValueError`` so the parser can treat
    a bad path as an invalid finding. The raw value is preserved separately in the
    reviewer's raw_response for audit; this never normalizes an arbitrary malformed
    path into a valid identity.
    """
    if not isinstance(value, str):
        raise ValueError("finding path must be a string")
    candidate = value
    if candidate.startswith("./"):
        candidate = candidate[2:]
    elif candidate.startswith(("a/", "b/")):
        candidate = candidate[2:]
    # "/dev/null" is caught by the leading-"/" rule; "dev/null" is a valid relative
    # path under the policy but is the conventional "no file" sentinel, not a target.
    if candidate == "dev/null":
        raise ValueError(f"unsafe finding path {value!r}: 'dev/null' is not a real file")
    error = _relative_path_error(candidate)
    if error is not None:
        raise ValueError(f"unsafe finding path {value!r}: {error}")
    return candidate


def _check_case_id(value: str) -> str:
    """Pydantic-facing validator: a case id is exactly one safe path component.

    It becomes a physical directory name, so it goes through the same component
    policy as a path segment (ASCII profile, no separators, no reserved device
    names even with an extension, no trailing dot or space, no leading dot) and is
    additionally required to start with an ASCII alphanumeric and stay within the
    case-id length bound.
    """
    error = _component_error(value)
    if error is not None:
        raise ValueError(f"unsafe case id {value!r}: {error}")
    if len(value) > _MAX_CASE_ID_LENGTH:
        raise ValueError(f"unsafe case id {value!r}: longer than {_MAX_CASE_ID_LENGTH} characters")
    if not (value[0].isascii() and value[0].isalnum()):
        raise ValueError(f"unsafe case id {value!r}: must start with an ASCII letter or digit")
    return value


SafeCaseId = Annotated[str, AfterValidator(_check_case_id)]


def validate_relative_path(value: str) -> str:
    """Domain wrapper for I/O-boundary callers: raises Arena ValidationError."""
    try:
        return _check_relative_path(value)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def validate_case_id(value: str) -> str:
    """Domain wrapper for I/O-boundary callers: raises Arena ValidationError."""
    try:
        return _check_case_id(value)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


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
