"""Isolated, bounded, read-only access to committed Git objects.

Reuses the Phase 1D Git subprocess isolation (private empty HOME/config, no hooks/
pager/editor/credentials/network, fixed locale, bounded incremental output, timeout
and process-group cleanup) rather than duplicating a weaker version. Reads only
committed objects (ls-tree / cat-file / diff between commits); it never runs
checkout/clone/fetch, repository code, or reads the mutable working tree.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from arena.core import limits
from arena.core.errors import ImportFixError
from arena.patching.git_pipeline import (
    _git_config,
    _git_env,
    _GitContext,
    _GitRunError,
    _run_git,
    _text,
)
from arena.security.paths import _relative_path_error

_FULL_OID = {"sha1": re.compile(r"\A[0-9a-f]{40}\Z"), "sha256": re.compile(r"\A[0-9a-f]{64}\Z")}
_ALLOWED_TREE_MODES = frozenset({"100644", "100755"})


@dataclass
class Repo:
    """An opened source repository plus its isolated Git context."""

    ctx: _GitContext
    object_format: str


def _git(repo: Repo, args: list[str], reason: str) -> bytes:
    try:
        rc, out, err = _run_git(repo.ctx, args)
    except _GitRunError as exc:
        raise ImportFixError(reason, exc.diagnostic or reason) from exc
    if rc != 0:
        raise ImportFixError(reason, _text(err) or _text(out) or reason)
    return out


@contextmanager
def open_repo(repo_path: Path) -> Iterator[Repo]:
    """Open ``repo_path`` (worktree or bare) under an isolated, bounded Git context."""
    repo_path = Path(repo_path)
    if not repo_path.exists():
        raise ImportFixError("repository_missing", f"repository path does not exist: {repo_path}")
    meta = Path(tempfile.mkdtemp(prefix="arena-import-git-"))
    home = meta / "home"
    hooks = meta / "hooks"
    home.mkdir()
    hooks.mkdir()
    (meta / "empty.gitconfig").write_text("", encoding="utf-8")
    ctx = _GitContext(
        cwd=repo_path,
        env=_git_env(home, meta / "empty.gitconfig", repo_path),
        config=_git_config(hooks),
        timeout=limits.GIT_TIMEOUT_SECONDS,
        scrub=(str(meta), str(home)),
    )
    try:
        rc, out, _err = _run_git(ctx, ["rev-parse", "--is-inside-work-tree", "--git-dir"])
        if rc != 0:
            # Could be a bare repository; confirm it is a Git repository of some kind.
            brc, _bo, _be = _run_git(ctx, ["rev-parse", "--git-dir"])
            if brc != 0:
                raise ImportFixError("not_a_git_repository", f"not a Git repository: {repo_path}")
        object_format = _text(
            _git(Repo(ctx, "sha1"), ["rev-parse", "--show-object-format"], "git_failed")
        )
        if object_format not in _FULL_OID:
            raise ImportFixError(
                "unsupported_object_format", f"unsupported format {object_format!r}"
            )
        yield Repo(ctx, object_format)
    except _GitRunError as exc:
        raise ImportFixError("git_failed", exc.diagnostic or "git failed") from exc
    finally:
        shutil.rmtree(meta, ignore_errors=True)


def resolve_commit(repo: Repo, oid: str) -> str:
    """Require a full object id (per the repo format) that names a commit object."""
    if not _FULL_OID[repo.object_format].match(oid):
        raise ImportFixError(
            "abbreviated_commit_id",
            f"commit id must be a full {repo.object_format} object id",
        )
    out = _git(repo, ["cat-file", "-t", oid], "invalid_commit_object")
    if _text(out) != "commit":
        raise ImportFixError("invalid_commit_object", "object id does not name a commit")
    # The verified id must equal the supplied id (no ref/peel resolution).
    verified = _text(
        _git(repo, ["rev-parse", "--verify", f"{oid}^{{commit}}"], "invalid_commit_object")
    )
    if verified != oid:
        raise ImportFixError("invalid_commit_object", "commit id did not resolve to itself")
    return oid


def is_ancestor(repo: Repo, ancestor: str, descendant: str) -> bool:
    rc, _o, _e = _run_git(repo.ctx, ["merge-base", "--is-ancestor", ancestor, descendant])
    return rc == 0


def merge_base(repo: Repo, a: str, b: str) -> str | None:
    rc, out, _e = _run_git(repo.ctx, ["merge-base", a, b])
    return _text(out) if rc == 0 and _text(out) else None


def read_tree(repo: Repo, commit: str, prefixes: list[str]) -> dict[str, tuple[str, str]]:
    """Map repo-relative path -> (mode, blob oid) for regular files under ``prefixes``.

    Rejects symlink/gitlink/submodule/unknown modes and unsafe paths.
    """
    out = _git(repo, ["ls-tree", "-rz", "--full-tree", commit, "--", *prefixes], "git_failed")
    entries: dict[str, tuple[str, str]] = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        try:
            meta, raw_path = record.split(b"\t", 1)
            mode, obj_type, oid = meta.decode("ascii").split(" ")
            path = raw_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ImportFixError("git_output_invalid", "malformed ls-tree record") from exc
        if obj_type != "blob" or mode not in _ALLOWED_TREE_MODES:
            raise ImportFixError(
                "unsupported_tree_mode", f"unsupported tree entry mode {mode} ({obj_type})"
            )
        if not _FULL_OID[repo.object_format].match(oid):
            raise ImportFixError("git_output_invalid", "malformed object id in tree")
        if _relative_path_error(path) is not None:
            raise ImportFixError("unsafe_tree_path", "tree contains an unsafe path")
        entries[path] = (mode, oid)
    return entries


def cat_blob(repo: Repo, oid: str) -> bytes:
    """Exact blob bytes (bounded by the Git runner's output ceiling)."""
    return _git(repo, ["cat-file", "blob", oid], "file_too_large")


def has_binary_change(repo: Repo, old: str, new: str, prefixes: list[str]) -> bool:
    """True when any changed source path between two commits is binary (numstat '-')."""
    out = _git(
        repo, ["diff", "--numstat", "-z", "--no-renames", old, new, "--", *prefixes], "git_failed"
    )
    # -z numstat: records are "added\tdeleted\t" then a NUL-separated path (or two for
    # renames, which are disabled). A binary file reports "-\t-\t".
    fields = out.split(b"\0")
    index = 0
    while index < len(fields):
        head = fields[index]
        if not head:
            index += 1
            continue
        try:
            added, deleted, _rest = head.decode("ascii", errors="replace").split("\t", 2)
        except ValueError:
            index += 1
            continue
        if added == "-" and deleted == "-":
            return True
        index += 1
    return False


def changed_paths(repo: Repo, old: str, new: str) -> set[str]:
    """Every repo-relative path changed between two commits (whole tree, renames off)."""
    from arena.patching.git_pipeline import _parse_raw_z

    out = _git(repo, ["diff", "--raw", "-z", "--no-renames", old, new], "git_failed")
    try:
        changes = _parse_raw_z(out, repo.object_format)
    except _GitRunError as exc:
        raise ImportFixError("git_output_invalid", exc.diagnostic or "bad diff output") from exc
    paths: set[str] = set()
    for change in changes:
        paths.add(change.new_path)
        if change.old_path is not None:
            paths.add(change.old_path)
    return paths


def diff_text(repo: Repo, old: str, new: str, prefixes: list[str]) -> bytes:
    """A textual unified diff old->new restricted to ``prefixes`` (renames disabled)."""
    return _git(
        repo,
        [
            "diff",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            old,
            new,
            "--",
            *prefixes,
        ],
        "git_failed",
    )
