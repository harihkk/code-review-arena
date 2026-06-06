"""Generate reference.patch gold artifacts for a benchmark pack.

A reference patch is the canonical known-good repair: the unified diff that turns
a case's buggy `after/` source into its fixed form. The fixed sources are the
single source of truth held in ``MockReviewer.FIXED_FILES``; this script renders
them as diffs so the ``reference-patch`` reviewer and the validator have a gold
artifact per case.

Idempotent: by default it skips cases that already ship a reference.patch (so it
never clobbers hand-authored patches). Pass --force to regenerate.
"""

from __future__ import annotations

import argparse
import difflib
from pathlib import Path

from arena.benchmark.case_loader import build_context, load_cases
from arena.reviewers.mock import MockReviewer
from arena.reviewers.reference_patch import REFERENCE_PATCH_FILENAME


def render_reference_patch(case_id: str, original: str) -> str:
    path = MockReviewer.ANSWERS[case_id][2]
    replacement = MockReviewer.FIXED_FILES[case_id]
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            replacement.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def generate(pack: Path, *, force: bool = False) -> list[str]:
    written: list[str] = []
    for case in load_cases(pack):
        if case.id not in MockReviewer.FIXED_FILES or case.id not in MockReviewer.ANSWERS:
            continue
        assert case.case_dir is not None
        target = case.case_dir / REFERENCE_PATCH_FILENAME
        if target.exists() and not force:
            continue
        path = MockReviewer.ANSWERS[case.id][2]
        original = build_context(case).relevant_files[path]
        target.write_text(render_reference_patch(case.id, original), encoding="utf-8")
        written.append(case.id)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack", type=Path, help="Benchmark pack directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing reference.patch files instead of skipping them",
    )
    args = parser.parse_args()
    written = generate(args.pack, force=args.force)
    if written:
        print(f"Wrote {len(written)} reference patch(es): {', '.join(written)}")
    else:
        print("No reference patches written (all present; use --force to regenerate).")


if __name__ == "__main__":
    main()
