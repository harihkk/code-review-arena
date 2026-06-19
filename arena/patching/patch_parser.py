"""Small, deterministic helpers for paths in unified diffs."""

from __future__ import annotations

from pathlib import PurePosixPath

# Diff lines that name filesystem paths. Renames/copies matter: git apply
# honors them even when no +++ hunk header references the target.
_PATH_PREFIXES = ("--- ", "+++ ", "rename from ", "rename to ", "copy from ", "copy to ")


def normalize_patch_path(path: str) -> str:
    """Remove git diff prefixes while retaining repository-relative paths."""
    clean = path.strip().split("\t", 1)[0].split(" ", 1)[0]
    if clean in {"/dev/null", "dev/null"}:
        return ""
    if clean.startswith(("a/", "b/")):
        return clean[2:]
    return clean


def touched_files(patch_text: str) -> list[str]:
    """Return normalized target paths referenced by a unified diff."""
    paths: list[str] = []
    for line in patch_text.splitlines():
        if not line.startswith("+++ "):
            continue
        path = normalize_patch_path(line[4:])
        if path and path not in paths:
            paths.append(path)
    return paths


def referenced_paths(patch_text: str) -> list[str]:
    """Every path a diff names: sources, targets, renames, and copies."""
    paths: list[str] = []
    for line in patch_text.splitlines():
        for prefix in _PATH_PREFIXES:
            if line.startswith(prefix):
                path = normalize_patch_path(line[len(prefix) :])
                if path and path not in paths:
                    paths.append(path)
                break
    return paths


def unsafe_patch_paths(patch_text: str) -> list[str]:
    """Paths that are absolute or escape the workspace via ``..`` segments."""
    unsafe: list[str] = []
    for path in referenced_paths(patch_text):
        pure = PurePosixPath(path)
        windows_drive = len(path) >= 2 and path[0].isalpha() and path[1] == ":"
        if pure.is_absolute() or windows_drive or ".." in pure.parts:
            unsafe.append(path)
    return unsafe


# Git file modes that are not regular files: a patch must not introduce a symlink
# (which could point outside the workspace) or a gitlink/submodule.
_UNSAFE_MODES = ("120000", "160000")


def unsafe_patch_modes(patch_text: str) -> list[str]:
    """Mode declarations in the diff that would create a symlink or gitlink."""
    found: list[str] = []
    for line in patch_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("new file mode ", "new mode ", "old mode ", "deleted file mode ")):
            mode = stripped.rsplit(" ", 1)[-1]
            if mode in _UNSAFE_MODES:
                found.append(stripped)
    return found
