"""Deterministic reverse-fix case generator.

Given a buggy commit B and a fixed commit F (B an ancestor of F) in a local Git
repository, generate a one-case candidate pack:

    after/           = selected source content at B (buggy)
    before/          = selected source content at F (fixed)
    reference.patch  = exact repair diff  B -> F   (after/ + reference.patch == F)
    pr.diff          = inverse review diff F -> B   (before/ + pr.diff == after/)
    tests/           = selected test content at F

This is a SYNTHETIC reverse-review case derived from a real historical fix; it is
not the original bug-introducing pull request. Generation is deterministic, local,
offline, non-AI, and does not execute repository code or certify the result.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from arena.benchmark.contamination import scan_benchmark
from arena.benchmark.dataset_validator import validate_dataset
from arena.benchmark.pack_hash import write_checksum
from arena.core import limits
from arena.core.errors import ImportFixError
from arena.importer import git_objects as g
from arena.importer.import_spec import ImportSpec, load_import_spec
from arena.patching.git_pipeline import apply_patch

PROVENANCE_SCHEMA_VERSION = "1"


@dataclass
class ImportResult:
    output_path: Path
    case_id: str
    buggy_commit: str
    fixed_commit: str
    merge_base: str
    object_format: str
    source_file_count: int
    test_file_count: int
    repair_changed_paths: list[str] = field(default_factory=list)
    test_changed_paths: list[str] = field(default_factory=list)
    pack_checksum: str = ""
    validation_ok: bool = False
    contamination_ok: bool = False
    certification: str = "not run"


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _materialize(
    repo: g.Repo, tree: dict[str, tuple[str, str]], dest_root: Path, counters: dict
) -> None:
    for path, (mode, oid) in sorted(tree.items()):
        data = g.cat_blob(repo, oid)
        counters["files"] += 1
        counters["bytes"] += len(data)
        if counters["files"] > limits.IMPORT_MAX_FILES:
            raise ImportFixError("output_write_failure", "too many files in the generated pack")
        if counters["bytes"] > limits.IMPORT_MAX_TOTAL_BYTES:
            raise ImportFixError("output_write_failure", "generated pack exceeds the byte limit")
        target = dest_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
        except OSError as exc:
            raise ImportFixError(
                "output_write_failure", "could not write a generated file"
            ) from exc
        os.chmod(target, 0o755 if mode == "100755" else 0o644)
        if target.lstat().st_size != len(data) or target.read_bytes() != data:
            raise ImportFixError("output_write_failure", "written file did not verify")


def _decode_diff(raw: bytes, label: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ImportFixError("invalid_diff_encoding", f"{label} is not valid UTF-8") from exc


def _tree_files(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for current, _dirs, files in os.walk(root):
        for name in files:
            p = Path(current) / name
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


def _verify_reproduces(source_dir: Path, patch_text: str, expected_dir: Path, reason: str) -> None:
    """Apply patch_text to source_dir via the Phase 1D pipeline; require == expected_dir."""
    with tempfile.TemporaryDirectory(prefix="arena-import-verify-") as tmp:
        dest = Path(tmp) / "ws"
        result = apply_patch(
            source_dir=source_dir, patch_text=patch_text, protected_paths=[], destination=dest
        )
        if not result.applied or result.workspace is None:
            raise ImportFixError(reason, f"authoritative apply failed: {result.reason}")
        if _tree_files(result.workspace) != _tree_files(expected_dir):
            raise ImportFixError(reason, "patched tree does not match the expected commit tree")


def _build_documents(
    spec: ImportSpec,
    *,
    buggy: str,
    fixed: str,
    base: str,
    object_format: str,
    source_label: str | None,
    repair_paths: list[str],
    test_paths: list[str],
    pr_diff_sha: str,
    reference_sha: str,
    has_tests: bool,
) -> tuple[str, str, str]:
    """Return (manifest_yaml, case_yaml, provenance_json) as deterministic text."""
    case = spec.to_case()
    # Validate the assembled case once here so a bad spec fails before any write.
    ground_truth = spec.ground_truth.model_dump(mode="json")
    ground_truth.pop("primary_bug", None)
    input_doc = {"diff": "pr.diff", "before_dir": "before", "after_dir": "after"}
    if has_tests:
        input_doc["tests_dir"] = "tests"
    case_doc = {
        "id": case.id,
        "title": case.title,
        "category": case.category,
        "severity": case.severity,
        "stack": list(case.stack),
        "description": case.description,
        "input": input_doc,
        "ground_truth": ground_truth,
        "scoring": spec.scoring.model_dump(mode="json"),
        "execution": spec.execution.model_dump(mode="json"),
        "validation": spec.validation.model_dump(mode="json"),
        "metrics": spec.metrics.model_dump(mode="json"),
    }
    manifest_doc = {"version": spec.pack.version, "name": spec.pack.name, "cases": [case.id]}
    provenance = {
        "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        "mode": "reverse_fix",
        "source_label": source_label,
        "object_format": object_format,
        "buggy_commit": buggy,
        "fixed_commit": fixed,
        "merge_base": base,
        "source_paths": sorted(spec.source_paths),
        "tests_root": spec.tests_root,
        "repair_changed_paths": sorted(repair_paths),
        "test_changed_paths": sorted(test_paths),
        "pr_diff_sha256": pr_diff_sha,
        "reference_patch_sha256": reference_sha,
    }
    manifest_yaml = yaml.safe_dump(manifest_doc, sort_keys=True, default_flow_style=False)
    case_yaml = yaml.safe_dump(case_doc, sort_keys=True, default_flow_style=False)
    provenance_json = json.dumps(provenance, sort_keys=True, indent=2) + "\n"
    return manifest_yaml, case_yaml, provenance_json


def import_fix(
    *,
    repo_path: Path,
    buggy_commit: str,
    fixed_commit: str,
    spec_path: Path,
    output: Path,
    source_label: str | None = None,
) -> ImportResult:
    """Generate a deterministic reverse-fix candidate pack. See module docstring."""
    output = Path(output)
    if output.exists():
        raise ImportFixError("output_exists", f"output already exists: {output}")
    if source_label is not None and len(source_label) > limits.IMPORT_SOURCE_LABEL_LEN:
        raise ImportFixError("invalid_spec", "source label is too long")
    spec = load_import_spec(Path(spec_path))
    if spec.execution.run_tests and not spec.tests_root:
        raise ImportFixError(
            "selected_path_missing", "run_tests is set but no tests_root was given"
        )

    source_paths = sorted(set(spec.source_paths))
    tests_root = spec.tests_root
    # Source and test selections must be disjoint.
    if tests_root is not None:
        for sp in source_paths:
            if _under(sp, tests_root) or _under(tests_root, sp):
                raise ImportFixError(
                    "source_test_overlap", f"source/tests overlap: {sp} vs {tests_root}"
                )

    with g.open_repo(Path(repo_path)) as repo:
        buggy = g.resolve_commit(repo, buggy_commit)
        fixed = g.resolve_commit(repo, fixed_commit)
        base = g.merge_base(repo, buggy, fixed)
        if base is None:
            raise ImportFixError("commits_unrelated", "buggy and fixed commits are unrelated")
        if not g.is_ancestor(repo, buggy, fixed):
            raise ImportFixError("fixed_not_descendant", "fixed commit is not descended from buggy")

        after_src = g.read_tree(repo, buggy, source_paths)  # B
        before_src = g.read_tree(repo, fixed, source_paths)  # F
        if not after_src and not before_src:
            raise ImportFixError("selected_path_missing", "no source files matched the selection")
        # Tests come from the fixed commit; their tests_root-relative paths are placed
        # under the case's tests/ directory (the contents of tests_root, not the prefix).
        tests_tree = g.read_tree(repo, fixed, [tests_root]) if tests_root else {}
        tests_materialize: dict[str, tuple[str, str]] = {}
        if tests_root is not None:
            for path, mode_oid in tests_tree.items():
                if path == tests_root:
                    rel = Path(tests_root).name
                elif path.startswith(tests_root + "/"):
                    rel = path[len(tests_root) + 1 :]
                else:  # pragma: no cover - ls-tree is restricted to the prefix
                    raise ImportFixError("selected_path_missing", "unexpected test path")
                tests_materialize[rel] = mode_oid

        # Classify every change B->F as selected-source or selected-tests; nothing silent.
        all_changed = g.changed_paths(repo, buggy, fixed)
        repair_paths: list[str] = []
        test_paths: list[str] = []
        unclassified: list[str] = []
        for path in sorted(all_changed):
            in_source = any(_under(path, sp) for sp in source_paths)
            in_tests = tests_root is not None and _under(path, tests_root)
            if in_source and in_tests:
                raise ImportFixError("source_test_overlap", f"changed path is in both: {path}")
            if in_source:
                repair_paths.append(path)
            elif in_tests:
                test_paths.append(path)
            else:
                unclassified.append(path)
        if unclassified:
            raise ImportFixError(
                "changed_path_unclassified",
                "changed paths outside source/tests selection: " + ", ".join(unclassified[:20]),
            )
        if g.has_binary_change(repo, buggy, fixed, source_paths):
            raise ImportFixError("binary_change", "binary source change is not supported")

        reference_patch = _decode_diff(
            g.diff_text(repo, buggy, fixed, source_paths), "reference.patch"
        )
        pr_diff = _decode_diff(g.diff_text(repo, fixed, buggy, source_paths), "pr.diff")
        reference_sha = hashlib.sha256(reference_patch.encode("utf-8")).hexdigest()
        pr_diff_sha = hashlib.sha256(pr_diff.encode("utf-8")).hexdigest()

        # Ground-truth admission against the buggy after/ tree and the synthetic review.
        bug_files = {f.path for bug in spec.ground_truth.bugs for f in bug.files}
        repair_set = set(repair_paths)
        for bug in spec.ground_truth.bugs:
            for gt_file in bug.files:
                if gt_file.path not in after_src:
                    raise ImportFixError(
                        "ground_truth_file_missing",
                        f"ground-truth file not in buggy source: {gt_file.path}",
                    )
                if gt_file.path not in repair_set:
                    raise ImportFixError(
                        "ground_truth_file_not_changed",
                        f"ground-truth file is not changed by the fix: {gt_file.path}",
                    )
        uncovered = sorted(repair_set - bug_files)
        if uncovered:
            raise ImportFixError(
                "semantic_change_uncovered",
                "repair paths not covered by any declared bug: " + ", ".join(uncovered[:20]),
            )

        staging = Path(tempfile.mkdtemp(prefix=".arena-import-", dir=str(output.parent)))
        try:
            case_dir = staging / spec.case.id
            after_dir = case_dir / "after"
            before_dir = case_dir / "before"
            counters = {"files": 0, "bytes": 0}
            _materialize(repo, after_src, after_dir, counters)
            _materialize(repo, before_src, before_dir, counters)
            if tests_materialize:
                _materialize(repo, tests_materialize, case_dir / "tests", counters)

            # Validate ground-truth line ranges against the materialized buggy files.
            for bug in spec.ground_truth.bugs:
                for gt_file in bug.files:
                    line_count = len(
                        (after_dir / gt_file.path).read_text(encoding="utf-8").splitlines()
                    )
                    for rng in gt_file.line_ranges:
                        if rng.end > line_count:
                            raise ImportFixError(
                                "invalid_ground_truth_range",
                                f"line range {rng.start}-{rng.end} exceeds {gt_file.path} "
                                f"({line_count} lines)",
                            )

            (case_dir / "reference.patch").write_text(reference_patch, encoding="utf-8")
            (case_dir / "pr.diff").write_text(pr_diff, encoding="utf-8")
            manifest_yaml, case_yaml, provenance_json = _build_documents(
                spec,
                buggy=buggy,
                fixed=fixed,
                base=base,
                object_format=repo.object_format,
                source_label=source_label,
                repair_paths=repair_paths,
                test_paths=test_paths,
                pr_diff_sha=pr_diff_sha,
                reference_sha=reference_sha,
                has_tests=bool(tests_tree),
            )
            (staging / "manifest.yaml").write_text(manifest_yaml, encoding="utf-8")
            (case_dir / "case.yaml").write_text(case_yaml, encoding="utf-8")
            (case_dir / "provenance.json").write_text(provenance_json, encoding="utf-8")

            # Authoritative reproduction proof through the Phase 1D pipeline.
            _verify_reproduces(
                after_dir, reference_patch, before_dir, "reference_patch_verification_failed"
            )
            _verify_reproduces(before_dir, pr_diff, after_dir, "pr_diff_verification_failed")

            checksum = write_checksum(staging)
            errors = validate_dataset(staging)
            if errors:
                raise ImportFixError("generated_pack_invalid", "; ".join(errors)[:512])
            warnings = scan_benchmark(staging)
            if warnings:
                raise ImportFixError(
                    "contamination_detected", f"{len(warnings)} contamination warning(s)"
                )
            os.replace(staging, output)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    return ImportResult(
        output_path=output,
        case_id=spec.case.id,
        buggy_commit=buggy,
        fixed_commit=fixed,
        merge_base=base,
        object_format=repo.object_format,
        source_file_count=len(after_src),
        test_file_count=len(tests_tree),
        repair_changed_paths=sorted(repair_paths),
        test_changed_paths=sorted(test_paths),
        pack_checksum=checksum,
        validation_ok=True,
        contamination_ok=True,
        certification="not run",
    )
