"""Git-authoritative patch application (Phase 1D).

Patch security and evidence previously depended on handwritten parsing of
reviewer diff text. This module instead treats the actual post-application Git
tree as authoritative: a candidate (or reference) patch is applied inside an
isolated Git repository, and what *actually changed* is read from Git
(`git diff --raw -z` between the baseline and result trees, plus the resulting
index), never from the patch text. The handwritten parser remains only for
non-authoritative diagnostics.

One shared transaction is used for every patch class (candidate repairs, the
canonical reference.patch, certification/determinism reference solutions, and any
patch-based mutation input), so a fix here protects them all.

Isolation: each transaction runs in a fresh private workspace copied from the
accepted Phase 1C snapshot subtree. Git metadata lives in a `.git` inside that
private workspace during the transaction and is removed before the workspace is
returned, so candidate code and tests never see `.git`, the index, the patch
input, or Git object storage. Every Git subprocess runs with a private empty
HOME, no system/global config, an empty hooks directory, no pager/editor/prompt,
no credential helpers, a fixed C locale, and a bounded timeout and output.

Scope: Git determines what actually changed; handwritten parsing is diagnostic
only. This does NOT isolate the reviewer process and does not make a self-reported
run official; later run-validity, execution and attestation phases remain pending.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from arena.core import limits
from arena.security.paths import _relative_path_error  # portable relative-path policy

GIT = "git"
# Diagnostics are bounded so unbounded Git output never lands in errors/evidence.
_DIAG_LEN = 2048

# Regular-file modes Arena accepts in a result tree. 120000 is a symlink, 160000 a
# gitlink/submodule; both are rejected, as is any other/unknown mode.
_ALLOWED_MODES = frozenset({"100644", "100755"})
_SYMLINK_MODE = "120000"
_GITLINK_MODE = "160000"

# Files that influence test collection or execution regardless of location; a patch
# may never create, modify, rename into/out of, or delete them. Git metadata control
# files are included so a patch can never introduce repository control content.
PROTECTED_BASENAMES = frozenset(
    {
        "conftest.py",
        "pytest.ini",
        "tox.ini",
        "setup.cfg",
        "pyproject.toml",
        "sitecustomize.py",
        "usercustomize.py",
        ".git",
        ".gitmodules",
        ".gitattributes",
    }
)


class _GitRunError(Exception):
    """Internal: a Git invocation failed in a way that maps to a stable reason code."""

    def __init__(self, reason: str, diagnostic: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.diagnostic = diagnostic[:_DIAG_LEN]


@dataclass(frozen=True)
class GitChange:
    """One authoritative change derived from Git (rename detection disabled)."""

    status: str  # A, M, D, T (R/C only if rename detection were enabled)
    old_mode: str
    new_mode: str
    old_sha: str
    new_sha: str
    old_path: str | None
    new_path: str


@dataclass
class GitPatchResult:
    """Structured, authoritative evidence for one patch transaction."""

    applied: bool
    reason: str | None = None
    patch_sha256: str | None = None
    git_version: str | None = None
    object_format: str | None = None
    baseline_tree: str | None = None
    result_tree: str | None = None
    changes: tuple[GitChange, ...] = ()
    touched_files: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    mode_changes: tuple[str, ...] = ()
    protected_violations: tuple[str, ...] = ()
    unsafe_paths: tuple[str, ...] = ()
    diagnostic: str | None = None
    duration_ms: int = 0
    workspace: Path | None = None


# --------------------------------------------------------------------------- #
# Isolated Git invocation                                                     #
# --------------------------------------------------------------------------- #


def _git_env(home: Path, empty_config: Path, ceiling: Path) -> dict[str, str]:
    env: dict[str, str] = {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(empty_config),
        "GIT_CONFIG_SYSTEM": str(empty_config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
        "GIT_EDITOR": "true",
        "GIT_ASKPASS": "true",
        "GIT_ALLOW_PROTOCOL": "",
        "GIT_CEILING_DIRECTORIES": str(ceiling),
        "LC_ALL": "C",
        "LANG": "C",
    }
    # Keep the minimum host vars Git needs to run, never user Git configuration.
    for key in ("PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "PATHEXT"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _git_config(hooks_dir: Path) -> list[str]:
    """Deterministic repository config passed as ``-c`` flags (highest precedence)."""
    return [
        "-c",
        f"core.hooksPath={hooks_dir}",
        "-c",
        "core.pager=",
        "-c",
        "core.autocrlf=false",
        "-c",
        "core.safecrlf=false",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.attributesfile=",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "gc.auto=0",
        "-c",
        "protocol.allow=never",
        "-c",
        "core.editor=true",
        "-c",
        "advice.detachedHead=false",
    ]


@dataclass
class _GitContext:
    cwd: Path
    env: dict[str, str]
    config: list[str]


def _run_git(ctx: _GitContext, args: list[str], *, stdin: bytes = b"") -> tuple[int, bytes, bytes]:
    """Run one bounded, isolated Git command; return (returncode, stdout, stderr)."""
    command = [GIT, *ctx.config, *args]
    popen_kwargs: dict[str, object] = {
        "cwd": str(ctx.cwd),
        "env": ctx.env,
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **popen_kwargs)  # type: ignore[call-overload]
    except FileNotFoundError as exc:
        raise _GitRunError("git_unavailable", "git executable not found") from exc
    try:
        out, err = process.communicate(input=stdin, timeout=limits.GIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        _terminate(process)
        raise _GitRunError("git_timeout", "git command timed out") from exc
    if len(out) > limits.GIT_OUTPUT_BYTES or len(err) > limits.GIT_OUTPUT_BYTES:
        raise _GitRunError("git_output_too_large", "git produced too much output")
    return process.returncode, out, err


def _terminate(process: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), 9)
        else:
            process.kill()
    except (ProcessLookupError, OSError):
        pass
    try:
        process.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError):
        pass


def _git_checked(ctx: _GitContext, args: list[str], reason: str, *, stdin: bytes = b"") -> bytes:
    rc, out, err = _run_git(ctx, args, stdin=stdin)
    if rc != 0:
        raise _GitRunError(reason, _text(err) or _text(out))
    return out


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


# --------------------------------------------------------------------------- #
# Workspace preparation                                                       #
# --------------------------------------------------------------------------- #


def _prepare_workspace(source_dir: Path, destination: Path) -> None:
    """Copy the snapshot subtree into a fresh destination and verify it is safe.

    Rejects symlinks, special files, and any ``.git`` entry before Git touches it.
    """
    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The source is a vetted Phase 1C snapshot subtree; copy without following links.
    shutil.copytree(source_dir, destination, symlinks=True)
    for current, dirnames, filenames in os.walk(destination):
        rel_root = Path(current)
        for name in [*dirnames, *filenames]:
            if name == ".git":
                raise _GitRunError("baseline_index_failed", "source contains a .git entry")
            info = (rel_root / name).lstat()
            if stat.S_ISLNK(info.st_mode):
                raise _GitRunError("baseline_index_failed", "source contains a symlink")
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise _GitRunError("baseline_index_failed", "source contains a special file")


# --------------------------------------------------------------------------- #
# Authoritative parsing                                                       #
# --------------------------------------------------------------------------- #


def _decode_path(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _GitRunError("unsafe_result_path", "git reported an undecodable path") from exc


def _parse_raw_z(data: bytes) -> list[GitChange]:
    """Parse ``git diff --raw -z`` records (rename detection disabled upstream)."""
    parts = data.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    changes: list[GitChange] = []
    index = 0
    while index < len(parts):
        meta = parts[index]
        if not meta.startswith(b":"):
            raise _GitRunError("git_output_invalid", "unexpected raw-diff record")
        try:
            fields = meta[1:].decode("ascii").split(" ")
        except UnicodeDecodeError as exc:
            raise _GitRunError("git_output_invalid", "non-ascii raw-diff metadata") from exc
        if len(fields) != 5:
            raise _GitRunError("git_output_invalid", "malformed raw-diff metadata")
        old_mode, new_mode, old_sha, new_sha, status = fields
        letter = status[:1]
        if letter in {"R", "C"}:
            if index + 2 >= len(parts):
                raise _GitRunError("git_output_invalid", "truncated rename record")
            change = GitChange(
                letter,
                old_mode,
                new_mode,
                old_sha,
                new_sha,
                _decode_path(parts[index + 1]),
                _decode_path(parts[index + 2]),
            )
            index += 3
        else:
            if index + 1 >= len(parts):
                raise _GitRunError("git_output_invalid", "truncated raw-diff record")
            path = _decode_path(parts[index + 1])
            change = GitChange(letter, old_mode, new_mode, old_sha, new_sha, None, path)
            index += 2
        changes.append(change)
    return changes


def _parse_ls_files_z(data: bytes) -> list[tuple[str, str, str]]:
    """Parse ``git ls-files -s -z`` into (mode, sha, path); reject unmerged stages."""
    parts = data.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    entries: list[tuple[str, str, str]] = []
    for record in parts:
        try:
            meta, raw_path = record.split(b"\t", 1)
        except ValueError as exc:
            raise _GitRunError("git_output_invalid", "malformed ls-files record") from exc
        try:
            mode, sha, stage = meta.decode("ascii").split()
        except (UnicodeDecodeError, ValueError) as exc:
            raise _GitRunError("git_output_invalid", "malformed ls-files metadata") from exc
        if stage != "0":
            raise _GitRunError("unmerged_index", "the index has unmerged stages")
        entries.append((mode, sha, _decode_path(raw_path)))
    return entries


# --------------------------------------------------------------------------- #
# Result policy                                                               #
# --------------------------------------------------------------------------- #


def _normalized_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _is_protected(path: str, protected: list[str]) -> bool:
    parts = path.split("/")
    if any(part in PROTECTED_BASENAMES for part in parts):
        return True
    for rule in protected:
        normalized = rule.strip("/")
        if normalized and (path == normalized or path.startswith(normalized + "/")):
            return True
    return False


def _changed_paths(change: GitChange) -> list[str]:
    paths = [change.new_path]
    if change.old_path is not None:
        paths.append(change.old_path)
    return paths


# --------------------------------------------------------------------------- #
# Filesystem equivalence                                                      #
# --------------------------------------------------------------------------- #


def _scan_workspace_files(destination: Path) -> set[str]:
    """Return relative POSIX paths of regular files; reject symlinks/special entries."""
    found: set[str] = set()
    for current, dirnames, filenames in os.walk(destination):
        if ".git" in dirnames:
            dirnames.remove(".git")  # never descend into Git metadata
        for name in filenames:
            path = Path(current) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise _GitRunError("unsafe_result_entry", "result contains a symlink")
            if not stat.S_ISREG(info.st_mode):
                raise _GitRunError("unsafe_result_entry", "result contains a special file")
            if info.st_nlink > 1:
                raise _GitRunError("unsafe_result_entry", "result contains a hardlink alias")
            found.add(path.relative_to(destination).as_posix())
    return found


def _check_status_clean(ctx: _GitContext) -> None:
    """Reject untracked files or any worktree/index divergence after application."""
    out = _git_checked(
        ctx, ["status", "--porcelain", "-z", "--untracked-files=all"], "git_output_invalid"
    )
    for record in out.split(b"\0"):
        if not record:
            continue
        code = record[:2]
        if code == b"??":
            raise _GitRunError("untracked_output", "patch produced an untracked file")
        if b"U" in code:
            raise _GitRunError("unmerged_index", "the index has unmerged stages")
        # Second column non-space means the worktree differs from the index.
        if len(code) >= 2 and code[1:2] != b" ":
            raise _GitRunError("index_worktree_mismatch", "worktree differs from the index")


def _validate_result(
    changes: list[GitChange], index: list[tuple[str, str, str]], protected: list[str]
) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """Apply path, mode, protection and collision policy; return categorized paths."""
    unsafe: list[str] = []
    protected_hits: list[str] = []
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    mode_changes: list[str] = []

    # Mode and per-change path/protection policy on the AUTHORITATIVE changes.
    for change in changes:
        for mode in (change.old_mode, change.new_mode):
            if mode == _SYMLINK_MODE:
                raise _GitRunError("unsafe_result_mode", "patch result introduces a symlink")
            if mode == _GITLINK_MODE:
                raise _GitRunError("unsafe_result_mode", "patch result introduces a gitlink")
            if mode != "000000" and mode not in _ALLOWED_MODES:
                raise _GitRunError("unsafe_result_mode", f"unsupported mode {mode}")
        for path in _changed_paths(change):
            if _relative_path_error(path) is not None:
                unsafe.append(path)
            if _is_protected(path, protected):
                protected_hits.append(path)
        if change.status == "A":
            added.append(change.new_path)
        elif change.status == "D":
            deleted.append(change.old_path or change.new_path)
        elif change.status == "T":
            mode_changes.append(change.new_path)
            modified.append(change.new_path)
        else:  # M and any residual R/C destination
            modified.append(change.new_path)
        if change.old_mode != change.new_mode and "000000" not in (
            change.old_mode,
            change.new_mode,
        ):
            mode_changes.append(change.new_path)

    if unsafe:
        raise _GitRunError("unsafe_result_path", "; ".join(sorted(set(unsafe)))[:_DIAG_LEN])
    if protected_hits:
        raise _GitRunError(
            "protected_path_changed", "; ".join(sorted(set(protected_hits)))[:_DIAG_LEN]
        )

    # The COMPLETE resulting index must be path-safe and collision-free, not only the
    # changed subset (a benign-looking change can collide with an existing entry).
    seen: dict[str, str] = {}
    for mode, _sha, path in index:
        if mode == _SYMLINK_MODE or mode == _GITLINK_MODE or mode not in _ALLOWED_MODES:
            raise _GitRunError("unsafe_result_mode", f"index entry has unsupported mode {mode}")
        if _relative_path_error(path) is not None:
            raise _GitRunError("unsafe_result_path", "index contains an unsafe path")
        key = _normalized_key(path)
        if key in seen and seen[key] != path:
            raise _GitRunError("path_collision", "index paths collide under normalization")
        seen[key] = path

    return added, modified, deleted, mode_changes, sorted({c.new_path for c in changes})


# --------------------------------------------------------------------------- #
# The transaction                                                             #
# --------------------------------------------------------------------------- #


def apply_patch(
    *, source_dir: Path, patch_text: str, protected_paths: list[str], destination: Path
) -> GitPatchResult:
    """Apply a patch to a private copy of ``source_dir``, authoritatively.

    On success the returned ``workspace`` is ``destination`` with the resulting
    source tree and no ``.git``. On any failure the destination is removed and the
    result carries a stable ``reason``. Patch-policy failures are results, not raised
    exceptions, so a run never crashes on a bad patch.
    """
    started = time.perf_counter()
    if not patch_text or not patch_text.strip():
        return GitPatchResult(applied=False, reason="no_patch_provided", duration_ms=_ms(started))
    patch_bytes = patch_text.encode("utf-8")
    if len(patch_bytes) > limits.PATCH_BYTES:
        return GitPatchResult(applied=False, reason="patch_too_large", duration_ms=_ms(started))
    patch_sha = hashlib.sha256(patch_bytes).hexdigest()

    meta = Path(tempfile.mkdtemp(prefix="arena-gitmeta-"))
    home = meta / "home"
    hooks = meta / "hooks"
    home.mkdir()
    hooks.mkdir()
    (meta / "empty.gitconfig").write_text("", encoding="utf-8")
    ctx = _GitContext(
        cwd=destination,
        env=_git_env(home, meta / "empty.gitconfig", destination.parent),
        config=_git_config(hooks),
    )
    try:
        _prepare_workspace(source_dir, destination)
        version_out = _git_checked(ctx, ["version"], "git_unavailable")
        git_version = _text(version_out)
        _git_checked(ctx, ["init", "-q"], "git_initialization_failed")
        object_format = _text(
            _git_checked(ctx, ["rev-parse", "--show-object-format"], "git_initialization_failed")
        )
        _git_checked(ctx, ["add", "-A"], "baseline_index_failed")
        baseline_tree = _text(_git_checked(ctx, ["write-tree"], "baseline_index_failed"))

        preflight_rc, _o, preflight_err = _run_git(
            ctx, ["apply", "--check", "--index", "--whitespace=nowarn", "-"], stdin=patch_bytes
        )
        if preflight_rc != 0:
            raise _GitRunError("patch_preflight_failed", _text(preflight_err))
        apply_rc, _o2, apply_err = _run_git(
            ctx, ["apply", "--index", "--whitespace=nowarn", "-"], stdin=patch_bytes
        )
        if apply_rc != 0:
            raise _GitRunError("patch_apply_failed", _text(apply_err))

        _check_status_clean(ctx)
        result_tree = _text(_git_checked(ctx, ["write-tree"], "result_tree_verification_failed"))
        raw = _git_checked(
            ctx,
            ["diff", "--raw", "-z", "--no-renames", "--full-index", baseline_tree, result_tree],
            "git_output_invalid",
        )
        changes = _parse_raw_z(raw)
        if len(changes) > limits.GIT_MAX_CHANGED_FILES:
            raise _GitRunError("git_output_too_large", "too many changed files")
        index = _parse_ls_files_z(_git_checked(ctx, ["ls-files", "-s", "-z"], "git_output_invalid"))
        if len(index) > limits.GIT_MAX_CHANGED_FILES:
            raise _GitRunError("git_output_too_large", "index too large")

        added, modified, deleted, mode_changes, touched = _validate_result(
            changes, index, protected_paths
        )

        # Filesystem equivalence: every workspace file is tracked, none extra, none
        # is a symlink/special/hardlink, and the worktree matches the index.
        workspace_files = _scan_workspace_files(destination)
        index_paths = {path for _m, _s, path in index}
        if workspace_files != index_paths:
            raise _GitRunError("index_worktree_mismatch", "workspace and index file sets differ")
        # Re-verify the result tree is stable.
        if (
            _text(_git_checked(ctx, ["write-tree"], "result_tree_verification_failed"))
            != result_tree
        ):
            raise _GitRunError("result_tree_verification_failed", "result tree changed")

        # Success: remove Git metadata so the returned workspace is source-only.
        shutil.rmtree(destination / ".git", ignore_errors=True)
        return GitPatchResult(
            applied=True,
            reason=None,
            patch_sha256=patch_sha,
            git_version=git_version,
            object_format=object_format,
            baseline_tree=baseline_tree,
            result_tree=result_tree,
            changes=tuple(changes),
            touched_files=tuple(touched),
            added=tuple(added),
            modified=tuple(modified),
            deleted=tuple(deleted),
            mode_changes=tuple(dict.fromkeys(mode_changes)),
            workspace=destination,
            duration_ms=_ms(started),
        )
    except _GitRunError as exc:
        shutil.rmtree(destination, ignore_errors=True)
        return GitPatchResult(
            applied=False,
            reason=exc.reason,
            patch_sha256=patch_sha,
            diagnostic=exc.diagnostic or None,
            protected_violations=(
                tuple(exc.diagnostic.split("; ")) if exc.reason == "protected_path_changed" else ()
            ),
            unsafe_paths=(
                tuple(exc.diagnostic.split("; ")) if exc.reason == "unsafe_result_path" else ()
            ),
            duration_ms=_ms(started),
        )
    finally:
        shutil.rmtree(meta, ignore_errors=True)


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
