"""Deterministic historical-fix importer: adversarial and integration tests.

Uses synthetic local Git repositories only (no network). Verifies reverse-fix
semantics, determinism, committed-object-only access, and safe rejection.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from arena.benchmark.contamination import scan_benchmark
from arena.benchmark.dataset_validator import validate_dataset
from arena.core import limits
from arena.core.errors import ImportFixError
from arena.importer.historical_fix import import_fix

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00",
    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00",
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True, env=_ENV
    ).stdout.strip()


def _supports_sha256() -> bool:
    import tempfile

    with tempfile.TemporaryDirectory() as probe:
        out = subprocess.run(
            ["git", "init", "--object-format=sha256", str(Path(probe) / "r")],
            capture_output=True,
            text=True,
        )
    return out.returncode == 0 and "unknown" not in (out.stderr or "").lower()


def _commit(
    repo: Path, files: dict[str, str], msg: str, *, modes: dict[str, int] | None = None
) -> str:
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="")
        if modes and rel in modes:
            os.chmod(p, modes[rel])
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path, name: str = "repo", object_format: str = "sha1") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", f"--object-format={object_format}")
    return repo


# A buggy->fixed pair: combine() subtracts, the fix makes it add. Ground-truth
# vocabulary is deliberately disjoint from the visible code/tests to stay clean.
_BUGGY = {"src/calc.py": "def combine(a, b):\n    return a - b\n"}
_FIXED = {"src/calc.py": "def combine(a, b):\n    return a + b\n"}
_TEST_SRC = "from src.calc import combine\n\n\ndef test_combine():\n    assert combine(2, 3) == 5\n"
_TEST = {"tests/test_calc.py": _TEST_SRC}

_SPEC = textwrap.dedent("""\
    schema_version: "1"
    pack: {version: "1", name: imported_fixes}
    case:
      id: calc_combine_sign_001
      title: Combine used subtraction
      category: correctness
      severity: high
      stack: [python]
      description: combine subtracted instead of summing.
    source_paths: [src]
    tests_root: tests
    ground_truth:
      bugs:
        - id: bug-1
          summary: wrong arithmetic operator
          files:
            - path: src/calc.py
              line_ranges: [{start: 1, end: 2}]
          concepts: [arithmetic]
          must_mention: [operator]
          acceptable_fix_keywords: [plus]
    execution: {run_tests: true, test_command: "pytest -q tests", timeout_seconds: 30}
    validation: {patch_required: true, tests_required: true}
""")


def _make(tmp_path, *, object_format="sha1", buggy=None, fixed=None, with_tests=True, modes=None):
    repo = _repo(tmp_path, object_format=object_format)
    files_b = dict(buggy or _BUGGY)
    files_f = dict(fixed or _FIXED)
    if with_tests:
        files_b.update(_TEST)
        files_f.update(_TEST)
    b = _commit(repo, files_b, "buggy", modes=modes)
    f = _commit(repo, files_f, "fix", modes=modes)
    return repo, b, f


def _spec_file(tmp_path, text=_SPEC) -> Path:
    p = tmp_path / "spec.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def _run(tmp_path, repo, b, f, *, out="out", spec=None, label="acme/calc"):
    return import_fix(
        repo_path=repo,
        buggy_commit=b,
        fixed_commit=f,
        spec_path=spec or _spec_file(tmp_path),
        output=tmp_path / out,
        source_label=label,
    )


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# --------------------------------------------------------------------------- #
# Determinism                                                                 #
# --------------------------------------------------------------------------- #


def test_deterministic_byte_identical(tmp_path):
    repo, b, f = _make(tmp_path)
    spec = _spec_file(tmp_path)
    r1 = _run(tmp_path, repo, b, f, out="a", spec=spec)
    r2 = _run(tmp_path, repo, b, f, out="b", spec=spec)
    assert r1.pack_checksum == r2.pack_checksum
    assert _tree(tmp_path / "a") == _tree(tmp_path / "b")


def test_dirty_worktree_does_not_affect_output(tmp_path):
    repo, b, f = _make(tmp_path)
    spec = _spec_file(tmp_path)
    clean = _run(tmp_path, repo, b, f, out="clean", spec=spec)
    (repo / "src" / "calc.py").write_text("GARBAGE\n")  # modify tracked file
    (repo / "untracked.py").write_text("junk\n")  # add untracked file
    dirty = _run(tmp_path, repo, b, f, out="dirty", spec=spec)
    assert clean.pack_checksum == dirty.pack_checksum
    assert _tree(tmp_path / "clean") == _tree(tmp_path / "dirty")


def test_no_volatile_data_in_provenance(tmp_path):
    repo, b, f = _make(tmp_path)
    _run(tmp_path, repo, b, f)
    text = (tmp_path / "out" / "calc_combine_sign_001" / "provenance.json").read_text()
    assert str(repo) not in text and str(tmp_path) not in text
    for forbidden in (
        "/Users",
        "/tmp",
        "/private",
        os.uname().nodename if hasattr(os, "uname") else "host",
    ):
        assert forbidden not in text


# --------------------------------------------------------------------------- #
# Commit identity                                                             #
# --------------------------------------------------------------------------- #


def test_full_sha1_ids_accepted(tmp_path):
    repo, b, f = _make(tmp_path)
    r = _run(tmp_path, repo, b, f)
    assert r.buggy_commit == b and r.fixed_commit == f and r.object_format == "sha1"


def test_abbreviated_id_rejected(tmp_path):
    repo, b, f = _make(tmp_path)
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b[:10], f)
    assert e.value.reason == "abbreviated_commit_id"


def test_branch_name_rejected(tmp_path):
    repo, b, f = _make(tmp_path)
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b, _git(repo, "rev-parse", "--abbrev-ref", "HEAD"))
    assert e.value.reason == "abbreviated_commit_id"


def test_non_commit_object_rejected(tmp_path):
    repo, b, f = _make(tmp_path)
    tree_oid = _git(repo, "rev-parse", "HEAD^{tree}")
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, tree_oid, f)
    assert e.value.reason == "invalid_commit_object"


def test_unrelated_commits_rejected(tmp_path):
    repo, b, f = _make(tmp_path)
    _git(repo, "checkout", "-q", "--orphan", "other")
    _git(repo, "rm", "-rfq", "--cached", ".")
    other = _commit(repo, {"unrelated.py": "x = 1\n"}, "orphan")
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, other, f)
    assert e.value.reason == "commits_unrelated"


def test_fixed_not_descendant_rejected(tmp_path):
    repo, b, f = _make(tmp_path)
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, f, b)  # swapped: buggy=F is not an ancestor of fixed=B
    assert e.value.reason == "fixed_not_descendant"


@pytest.mark.skipif(not _supports_sha256(), reason="git lacks sha256 object format")
def test_sha256_repository(tmp_path):
    repo, b, f = _make(tmp_path, object_format="sha256")
    assert len(b) == 64
    r = _run(tmp_path, repo, b, f)
    assert r.object_format == "sha256" and r.validation_ok


# --------------------------------------------------------------------------- #
# Tree safety                                                                 #
# --------------------------------------------------------------------------- #


def test_executable_source_file_supported(tmp_path):
    repo, b, f = _make(
        tmp_path,
        buggy={"src/calc.py": "def combine(a, b):\n    return a - b\n", "src/run.sh": "echo hi\n"},
        fixed={"src/calc.py": "def combine(a, b):\n    return a + b\n", "src/run.sh": "echo hi\n"},
        modes={"src/run.sh": 0o755},
    )
    r = _run(tmp_path, repo, b, f)
    assert r.validation_ok


def test_symlink_in_tree_rejected(tmp_path):
    repo = _repo(tmp_path)
    (repo / "src").mkdir()
    (repo / "src" / "calc.py").write_text("def combine(a, b):\n    return a - b\n")
    os.symlink("calc.py", repo / "src" / "link.py")
    b = _commit(repo, {}, "buggy-with-symlink")
    (repo / "src" / "calc.py").write_text("def combine(a, b):\n    return a + b\n")
    f = _commit(repo, {}, "fix")
    with pytest.raises(ImportFixError) as e:
        import_fix(
            repo_path=repo,
            buggy_commit=b,
            fixed_commit=f,
            spec_path=_spec_file(tmp_path),
            output=tmp_path / "out",
        )
    assert e.value.reason == "unsupported_tree_mode"


def test_oversized_pack_rejected(tmp_path, monkeypatch):
    repo, b, f = _make(tmp_path)
    monkeypatch.setattr(limits, "IMPORT_MAX_FILES", 1)
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b, f)
    assert e.value.reason == "output_write_failure"


# --------------------------------------------------------------------------- #
# Classification                                                              #
# --------------------------------------------------------------------------- #


def test_changed_path_outside_selection_rejected(tmp_path):
    # A change to docs/ is neither source (src) nor tests (tests): must fail loudly.
    repo, b, f = _make(
        tmp_path,
        buggy={"src/calc.py": "def combine(a, b):\n    return a - b\n", "docs/x.md": "old\n"},
        fixed={"src/calc.py": "def combine(a, b):\n    return a + b\n", "docs/x.md": "new\n"},
    )
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b, f)
    assert e.value.reason == "changed_path_unclassified"


def test_source_tests_overlap_rejected(tmp_path):
    repo, b, f = _make(tmp_path)
    bad = _SPEC.replace("source_paths: [src]", "source_paths: [src, tests]")
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b, f, spec=_spec_file(tmp_path, bad))
    assert e.value.reason == "source_test_overlap"


def test_source_plus_tests_change(tmp_path):
    # Both source and tests change between B and F; both classify, nothing unclassified.
    repo = _repo(tmp_path)
    one = "from src.calc import combine\n\n\ndef test_one():\n    assert combine(2, 3) == 5\n"
    two = one + "\n\ndef test_two():\n    assert combine(0, 0) == 0\n"
    b = _commit(
        repo,
        {"src/calc.py": "def combine(a, b):\n    return a - b\n", "tests/test_calc.py": one},
        "buggy",
    )
    f = _commit(
        repo,
        {"src/calc.py": "def combine(a, b):\n    return a + b\n", "tests/test_calc.py": two},
        "fix",
    )
    r = _run(tmp_path, repo, b, f, out="spt")
    assert r.source_file_count >= 1 and r.test_file_count >= 1
    assert "src/calc.py" in r.repair_changed_paths
    assert any(p.startswith("tests/") for p in r.test_changed_paths)


# --------------------------------------------------------------------------- #
# Generated semantics                                                         #
# --------------------------------------------------------------------------- #


def test_reverse_fix_semantics(tmp_path):
    repo, b, f = _make(tmp_path)
    _run(tmp_path, repo, b, f)
    case = tmp_path / "out" / "calc_combine_sign_001"
    assert "return a - b" in (case / "after" / "src" / "calc.py").read_text()  # buggy
    assert "return a + b" in (case / "before" / "src" / "calc.py").read_text()  # fixed
    assert (case / "tests" / "test_calc.py").exists()  # tests from fixed
    assert (case / "reference.patch").read_text().strip()
    assert (case / "pr.diff").read_text().strip()


def test_uncovered_repair_path_rejected(tmp_path):
    # The fix changes two source files but ground truth declares only one bug file.
    repo, b, f = _make(
        tmp_path,
        buggy={
            "src/calc.py": "def combine(a, b):\n    return a - b\n",
            "src/other.py": "VALUE = 1\n",
        },
        fixed={
            "src/calc.py": "def combine(a, b):\n    return a + b\n",
            "src/other.py": "VALUE = 2\n",
        },
    )
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b, f)
    assert e.value.reason == "semantic_change_uncovered"


def test_ground_truth_file_not_changed_rejected(tmp_path):
    repo, b, f = _make(tmp_path)
    bad = _SPEC.replace("path: src/calc.py", "path: src/missing.py")
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b, f, spec=_spec_file(tmp_path, bad))
    assert e.value.reason in {"ground_truth_file_missing", "ground_truth_file_not_changed"}


# --------------------------------------------------------------------------- #
# Integration                                                                 #
# --------------------------------------------------------------------------- #


def test_generated_pack_validates_and_is_clean(tmp_path):
    repo, b, f = _make(tmp_path)
    r = _run(tmp_path, repo, b, f)
    assert validate_dataset(tmp_path / "out") == []
    assert scan_benchmark(tmp_path / "out") == []
    assert r.validation_ok and r.contamination_ok and r.certification == "not run"


def test_output_overwrite_refused(tmp_path):
    repo, b, f = _make(tmp_path)
    spec = _spec_file(tmp_path)
    _run(tmp_path, repo, b, f, out="once", spec=spec)
    with pytest.raises(ImportFixError) as e:
        _run(tmp_path, repo, b, f, out="once", spec=spec)
    assert e.value.reason == "output_exists"


def test_cli_help_smoke():
    from typer.testing import CliRunner

    from arena.cli.main import app

    result = CliRunner().invoke(app, ["import-fix", "--help"])
    assert result.exit_code == 0
    assert "--buggy-commit" in result.output and "--fixed-commit" in result.output


@pytest.mark.skipif(os.name != "posix", reason="local execution is POSIX-only")
def test_generated_case_is_execution_valid(tmp_path):
    # The buggy after/ fails its tests; applying the generated reference.patch through
    # the Phase 1D pipeline repairs it so the tests pass -- a full execution-backed run.
    from arena.benchmark.benchmark_runner import run_benchmark
    from arena.core.registry import create_reviewer

    repo, b, f = _make(tmp_path)
    _run(tmp_path, repo, b, f)
    run = run_benchmark(
        tmp_path / "out",
        create_reviewer("reference-patch"),
        output_dir=tmp_path / "runs",
        persist=False,
        mode="full",
        allow_local_execution=True,
    )
    case = run.case_results[0]
    assert case.patch_applied is True
    assert case.tests_passed is True
