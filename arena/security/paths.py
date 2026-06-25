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
digits, ``_``, ``-``, ``.``, ``+`` and ``/``. We do not support Unicode filenames
in pack paths (no concrete need), which removes whole classes of confusable and
normalization attacks rather than blacklisting examples. Case-insensitive and
Unicode-normalization collisions are enforced again at snapshot construction
(Phase 1C). If Unicode paths ever become a requirement, the exact normalization
and confusable profile must be defined before relaxing this.

A dot-prefixed component is admitted only as an ordinary final leaf filename (for
example ``tests/.coveragerc``); dot-prefixed directory components and the reserved
repository-control names (``.git``, ``.hg``, ``.svn``, ``.gitignore``,
``.gitattributes``, ``.gitmodules``) stay rejected, so a hidden directory or a
VCS-control file cannot enter a pack or influence patch application. The pack
checksum covers every regular file including hidden leaf files (Phase 1C), so a
hidden leaf is not outside the digest. A case id is stricter still (see
``_check_case_id``): it admits no ``+`` and no leading dot.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator

from arena.core.errors import ValidationError

# Two ASCII component profiles. Ordinary relative-path components admit '+' (e.g.
# upstream fixture directories such as ``html+django``); a case id, which becomes a
# physical directory name and an identifier, stays on the narrower profile and
# admits no '+'. The two share the structural checks in ``_component_common_error``
# so their filesystem rules cannot drift.
_ALLOWED_PATH_COMPONENT_CHARS = re.compile(r"\A[A-Za-z0-9_.+-]+\Z")
_ALLOWED_CASE_ID_CHARS = re.compile(r"\A[A-Za-z0-9_.-]+\Z")
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
# Repository-control names whose mere presence can steer a VCS during patch
# application (``git add``/``apply`` reads ``.gitignore``/``.gitattributes``/
# ``.gitmodules``; a ``.git`` tree is the repository itself). Rejected wherever they
# appear -- leaf or directory -- so an upstream tree cannot smuggle one in.
_RESERVED_CONTROL_NAMES = frozenset(
    {".git", ".hg", ".svn", ".gitignore", ".gitattributes", ".gitmodules"}
)


def _component_common_error(component: object) -> str | None:
    """Structural checks shared by every path component and case id (charset aside)."""
    if not isinstance(component, str) or not component:
        return "empty component"
    if len(component) > _MAX_COMPONENT_LENGTH:
        return f"component longer than {_MAX_COMPONENT_LENGTH} characters"
    if component in {".", ".."}:
        return "'.' and '..' are not valid components"
    if component in _RESERVED_CONTROL_NAMES:
        return f"'{component}' is a reserved repository-control name"
    if component.endswith(".") or component.endswith(" "):
        return "a component may not end with a dot or space"
    if component.split(".")[0].upper() in _WINDOWS_RESERVED:
        return f"'{component}' uses a reserved device name"
    return None


def _path_component_error(component: object, *, is_final: bool) -> str | None:
    """Return why a relative-path component is unsafe, or None.

    Profile: ASCII letters, digits, ``_``, ``-``, ``.`` and ``+``. A dot-prefixed
    component is admitted only as an ordinary final leaf filename with a name after
    the dot (e.g. ``.coveragerc``); dot-prefixed directory components and reserved
    control names stay rejected.
    """
    error = _component_common_error(component)
    if error is not None:
        return error
    assert isinstance(component, str)  # narrowed by _component_common_error
    if component.startswith("."):
        if not is_final:
            return "a dot-prefixed component may only be a final leaf filename"
        if len(component) < 2:
            return "a dot-prefixed component must have a name after the dot"
    if not _ALLOWED_PATH_COMPONENT_CHARS.match(component):
        return "only ASCII letters, digits, '_', '-', '.', and '+' are allowed"
    return None


def _case_id_component_error(component: object) -> str | None:
    """Return why a case-id component is unsafe, or None.

    Stricter than a path component: no ``+`` and no leading dot (no hidden/leaf
    exception), because a case id becomes a physical directory name and identifier.
    """
    error = _component_common_error(component)
    if error is not None:
        return error
    assert isinstance(component, str)  # narrowed by _component_common_error
    if component.startswith("."):
        return "a case id may not start with a dot"
    if not _ALLOWED_CASE_ID_CHARS.match(component):
        return "only ASCII letters, digits, '_', '-', and '.' are allowed"
    return None


def _relative_path_error(value: object) -> str | None:
    """Return why ``value`` is not a safe portable relative path, or None if it is."""
    if not isinstance(value, str) or not value:
        return "empty path"
    if len(value) > _MAX_PATH_LENGTH:
        return f"path longer than {_MAX_PATH_LENGTH} characters"
    if value.startswith("/") or value.endswith("/"):
        return "leading or trailing '/' is not allowed"
    components = value.split("/")
    final_index = len(components) - 1
    for index, component in enumerate(components):
        error = _path_component_error(component, is_final=index == final_index)
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


def admit_reviewer_path(value: object, known_paths: frozenset[str] | None = None) -> str:
    """Admit a reviewer-supplied finding path to a canonical pack-relative path.

    ``Finding.file`` is reviewer-controlled. A leading ``./`` is always removed and
    the complete remaining path must satisfy the SAME portable relative-path policy
    as pack paths (ASCII profile, no traversal, no absolute/UNC/drive/backslash/
    control/dot-prefixed components, not ``dev/null``).

    A Git-style ``a/`` or ``b/`` prefix is only resolved against ``known_paths`` --
    the reviewer-visible repository paths (relevant-files keys plus diff-referenced
    paths) -- so a real top-level ``a/`` or ``b/`` directory is not corrupted:

        complete known, stripped unknown -> keep complete
        complete unknown, stripped known -> use stripped
        both known                       -> reject as ambiguous
        neither known                    -> keep complete

    With no ``known_paths`` context, the prefix is never stripped. Raises
    ``ValueError`` so the parser can treat a bad or ambiguous path as an invalid
    finding; the raw value is preserved in the reviewer's raw_response for audit.
    """
    if not isinstance(value, str):
        raise ValueError("finding path must be a string")
    candidate = value[2:] if value.startswith("./") else value
    if candidate == "dev/null":
        raise ValueError(f"unsafe finding path {value!r}: 'dev/null' is not a real file")
    error = _relative_path_error(candidate)
    if error is not None:
        raise ValueError(f"unsafe finding path {value!r}: {error}")
    if known_paths is None or not candidate.startswith(("a/", "b/")):
        return candidate
    stripped = candidate[2:]
    complete_known = candidate in known_paths
    stripped_known = (
        bool(stripped) and _relative_path_error(stripped) is None and stripped in known_paths
    )
    if complete_known and stripped_known:
        raise ValueError(
            f"ambiguous finding path {value!r}: both prefixed and stripped forms exist"
        )
    if stripped_known and not complete_known:
        return stripped
    return candidate


def _check_case_id(value: str) -> str:
    """Pydantic-facing validator: a case id is exactly one safe path component.

    It becomes a physical directory name, so it goes through the stricter case-id
    component policy (narrower ASCII profile with no ``+``, no separators, no
    reserved device or repository-control names, no trailing dot or space, no
    leading dot) and is additionally required to start with an ASCII alphanumeric
    and stay within the case-id length bound. Unlike an ordinary relative-path leaf,
    a case id never admits a dot-prefixed name.
    """
    error = _case_id_component_error(value)
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
