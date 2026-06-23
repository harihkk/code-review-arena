"""Generate patches in a fresh, isolated Git repository.

Diffs are never generated inside the source repository: instead the exact selected
B and F blob bytes are staged into a brand-new private repository (empty local/
global/system config, empty ``info/attributes``, no worktree, no hooks/filters/
external-diff/textconv/replacement refs) and diffed there with explicit
deterministic flags. So repository attributes, local diff configuration, and
history overrides in the source cannot affect the generated ``pr.diff`` /
``reference.patch``.
"""

from __future__ import annotations

import shutil
import tempfile
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

# Explicit, deterministic diff flags -- never rely on unspecified Git defaults.
_DIFF_FLAGS = [
    "--text",
    "--no-color",
    "--no-ext-diff",
    "--no-textconv",
    "--no-renames",
    "--default-prefix",
    "--full-index",
    "--unified=3",
    "--diff-algorithm=myers",
    "--no-indent-heuristic",
]

# Tree of selected files: relative path -> (mode, exact bytes).
SelectedTree = dict[str, tuple[str, bytes]]


def _run(ctx: _GitContext, args: list[str], reason: str, *, stdin: bytes = b"") -> bytes:
    try:
        rc, out, err = _run_git(ctx, args, stdin=stdin)
    except _GitRunError as exc:
        raise ImportFixError(reason, exc.diagnostic or reason) from exc
    if rc != 0:
        raise ImportFixError(reason, _text(err) or _text(out) or reason)
    return out


def _stage_tree(base_ctx: _GitContext, index_path: Path, files: SelectedTree) -> str:
    """Stage exact bytes into a private index, prove they round-trip, return the tree id."""
    ctx = _GitContext(
        cwd=base_ctx.cwd,
        env={**base_ctx.env, "GIT_INDEX_FILE": str(index_path)},
        config=base_ctx.config,
        timeout=base_ctx.timeout,
        scrub=base_ctx.scrub,
    )
    for path, (mode, data) in sorted(files.items()):
        oid = _text(
            _run(
                ctx,
                ["hash-object", "-w", "--no-filters", "--stdin"],
                "diff_repo_failed",
                stdin=data,
            )
        )
        _run(
            ctx,
            ["update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}"],
            "diff_repo_failed",
        )
        # Prove the staged blob is the exact input bytes (no filter/eol transformation).
        if _run(ctx, ["cat-file", "blob", oid], "diff_repo_failed") != data:
            raise ImportFixError("diff_repo_failed", "staged blob does not equal the source bytes")
    return _text(_run(ctx, ["write-tree"], "diff_repo_failed"))


def generate_patches(
    object_format: str, buggy_tree: SelectedTree, fixed_tree: SelectedTree
) -> tuple[str, str]:
    """Return (reference_patch B->F, pr_diff F->B) generated in an isolated repo.

    ``buggy_tree`` is the selected source at B; ``fixed_tree`` is the selected source
    at F. Both are staged and diffed inside a fresh, attribute-free repository.
    """
    meta = Path(tempfile.mkdtemp(prefix="arena-import-diff-"))
    repo = meta / "repo"
    home = meta / "home"
    hooks = meta / "hooks"
    repo.mkdir()
    home.mkdir()
    hooks.mkdir()
    (meta / "empty.gitconfig").write_text("", encoding="utf-8")
    base = _GitContext(
        cwd=repo,
        env=_git_env(home, meta / "empty.gitconfig", repo),
        config=_git_config(hooks),
        timeout=limits.GIT_TIMEOUT_SECONDS,
        scrub=(str(meta), str(home)),
    )
    try:
        _run(base, ["init", "-q", f"--object-format={object_format}"], "diff_repo_failed")
        # Belt and suspenders: an empty attributes file so nothing is interpreted.
        (repo / ".git" / "info").mkdir(parents=True, exist_ok=True)
        (repo / ".git" / "info" / "attributes").write_text("", encoding="utf-8")
        tree_b = _stage_tree(base, meta / "index-b", buggy_tree)
        tree_f = _stage_tree(base, meta / "index-f", fixed_tree)
        reference = _run(base, ["diff", *_DIFF_FLAGS, tree_b, tree_f], "diff_repo_failed")
        pr_diff = _run(base, ["diff", *_DIFF_FLAGS, tree_f, tree_b], "diff_repo_failed")
        return _decode(reference, "reference.patch"), _decode(pr_diff, "pr.diff")
    finally:
        shutil.rmtree(meta, ignore_errors=True)


def _decode(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ImportFixError("invalid_diff_encoding", f"{label} is not valid UTF-8") from exc
