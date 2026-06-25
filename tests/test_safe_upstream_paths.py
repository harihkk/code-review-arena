"""Ordinary upstream test content must survive every path-handling layer.

The path policy admits an ordinary final dot-leaf file (e.g. ``tests/.coveragerc``)
and the ``+`` character in a non-case path component (e.g. ``html+django``), while
still rejecting hidden directories, reserved VCS-control names, and the existing
traversal/charset/Windows-portability classes. These tests pin both the acceptance
of the two real upstream paths through validation, snapshot, manifest, checksum,
deterministic rebuild, diff parsing, patch application, and reviewer-path admission,
and the continued rejection of the unsafe forms.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from arena.benchmark.pack_hash import pack_checksum, stored_checksum, write_checksum
from arena.benchmark.snapshot import manifest_digest, snapshot_pack
from arena.core.errors import ValidationError
from arena.core.models import CaseInput, GroundTruthFile
from arena.patching.patch_applier import PatchApplier
from arena.patching.patch_models import PatchApplyRequest
from arena.patching.patch_parser import touched_files
from arena.security.paths import (
    admit_reviewer_path,
    validate_case_id,
    validate_dir_path,
    validate_relative_path,
)

DOTFILE = "tests/.coveragerc"
PLUS_PATH = "tests/examplefiles/html+django/input.txt"
UPSTREAM_PATHS = [DOTFILE, PLUS_PATH]


# -- 1. relative-path validation -----------------------------------------------


@pytest.mark.parametrize("path", UPSTREAM_PATHS)
def test_relative_path_validation_accepts(path):
    assert validate_relative_path(path) == path


# -- 2-4. snapshot traversal, manifest, checksum, deterministic rebuild ---------


def _pack_with_upstream_files(root: Path) -> Path:
    (root / "after").mkdir(parents=True)
    (root / "after" / "code.py").write_text("X = 1\n")
    for rel in UPSTREAM_PATHS:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("upstream\n")
    return root


def test_snapshot_traversal_and_manifest_include_upstream_paths(tmp_path):
    pack = _pack_with_upstream_files(tmp_path / "pack")
    with snapshot_pack(pack) as snap:
        manifest_paths = {entry.path for entry in snap.manifest}
    for rel in UPSTREAM_PATHS:
        assert rel in manifest_paths


def test_checksum_covers_and_verifies_upstream_paths(tmp_path):
    pack = _pack_with_upstream_files(tmp_path / "pack")
    base = pack_checksum(pack)
    # Each upstream file is covered: removing one moves the digest.
    (pack / DOTFILE).unlink()
    assert pack_checksum(pack) != base
    (pack / DOTFILE).write_text("upstream\n")
    assert pack_checksum(pack) == base
    # write_checksum verifies through a re-snapshot, then the stored value matches.
    intended = write_checksum(pack)
    assert stored_checksum(pack) == intended == base
    with snapshot_pack(pack) as snap:
        assert snap.checksum == intended


def test_deterministic_rebuild_is_stable_with_upstream_paths(tmp_path):
    pack = _pack_with_upstream_files(tmp_path / "pack")
    with snapshot_pack(pack) as first:
        digest_a, checksum_a = first.manifest_digest, first.checksum
    with snapshot_pack(pack) as second:
        digest_b, checksum_b = second.manifest_digest, second.checksum
    assert digest_a == digest_b
    assert checksum_a == checksum_b
    assert manifest_digest(tuple()) != digest_a  # sanity: digest is content-derived


# -- 5. diff parsing -----------------------------------------------------------


def _one_line_diff(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-upstream\n"
        "+patched\n"
    )


@pytest.mark.parametrize("path", UPSTREAM_PATHS)
def test_diff_parsing_recovers_upstream_paths(path):
    assert touched_files(_one_line_diff(path)) == [path]


# -- 6. patch application ------------------------------------------------------


@pytest.mark.parametrize("path", UPSTREAM_PATHS)
def test_patch_application_handles_upstream_paths(tmp_path, monkeypatch, path):
    source = tmp_path / "src"
    target = source / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("upstream\n")
    monkeypatch.chdir(tmp_path)
    result = PatchApplier(Path("runs")).apply(
        PatchApplyRequest(
            case_id="upstream_paths_001",
            source_dir=source.resolve(),
            patch_text=_one_line_diff(path),
            run_id="run1",
        )
    )
    assert result.applied is True
    assert result.touched_files == [path]
    applied = (tmp_path / "runs/run1/workspaces/upstream_paths_001" / path).read_text(
        encoding="utf-8"
    )
    assert applied == "patched\n"


# -- 7. reviewer-path admission ------------------------------------------------


def test_reviewer_path_admission_accepts_non_dot_without_known_paths():
    # An ordinary (non-dot) file is admitted without known-path context.
    assert admit_reviewer_path(PLUS_PATH) == PLUS_PATH
    assert admit_reviewer_path(f"./{PLUS_PATH}") == PLUS_PATH


def test_reviewer_dotfile_requires_known_file():
    known = frozenset({DOTFILE})
    # 1-2. accepted when it exactly appears in known_paths
    assert admit_reviewer_path(DOTFILE, known) == DOTFILE
    assert admit_reviewer_path(".coveragerc", frozenset({".coveragerc"})) == ".coveragerc"
    assert admit_reviewer_path(f"./{DOTFILE}", known) == DOTFILE
    # 3. rejected without known_paths
    with pytest.raises(ValueError):
        admit_reviewer_path(DOTFILE)
    # 4. unknown hidden path rejected even with a known set that lacks it
    with pytest.raises(ValueError):
        admit_reviewer_path(".hidden", known)


def test_reviewer_known_path_prefix_and_ambiguity_preserved():
    # 5. a/ and b/ and ./ normalization still works against known paths
    known = frozenset({"app/x.py"})
    assert admit_reviewer_path("b/app/x.py", known) == "app/x.py"
    assert admit_reviewer_path("./app/x.py") == "app/x.py"
    # 6. ambiguous normalized matches remain rejected
    ambiguous = frozenset({"a/x.py", "x.py"})
    with pytest.raises(ValueError):
        admit_reviewer_path("a/x.py", ambiguous)


# -- 8. directory-valued model fields reject every dot-prefixed component -------

DOT_DIRS = [".hidden", "src/.hidden", ".tests", "tests/.fixtures"]


@pytest.mark.parametrize("value", DOT_DIRS)
def test_directory_validator_rejects_dot_components(value):
    with pytest.raises(ValidationError):
        validate_dir_path(value)


@pytest.mark.parametrize("value", DOT_DIRS)
@pytest.mark.parametrize("field", ["before_dir", "after_dir", "tests_dir"])
def test_case_input_directory_fields_reject_dot_dirs(field, value):
    with pytest.raises(PydanticValidationError):
        CaseInput(**{field: value})


def test_case_input_directory_fields_accept_normal_dirs():
    ci = CaseInput(before_dir="before", after_dir="after", tests_dir="tests")
    assert (ci.before_dir, ci.after_dir, ci.tests_dir) == ("before", "after", "tests")


def test_directory_field_rejects_dot_leaf_that_a_file_field_accepts():
    # The exact file-vs-directory distinction: a final dot-leaf is a valid FILE path
    # but rejected as a directory path.
    assert validate_relative_path("tests/.coveragerc") == "tests/.coveragerc"
    assert GroundTruthFile(path="tests/.coveragerc", line_ranges=[{"start": 1, "end": 1}]).path == (
        "tests/.coveragerc"
    )
    with pytest.raises(ValidationError):
        validate_dir_path("tests/.coveragerc")
    with pytest.raises(PydanticValidationError):
        CaseInput(tests_dir="tests/.coveragerc")


# -- 9. repository-control names rejected case-insensitively -------------------

CONTROL_NAMES = [".git", ".hg", ".svn", ".gitignore", ".gitattributes", ".gitmodules"]


def _casings(name):
    return [name, name.upper(), "." + name[1:].capitalize()]


@pytest.mark.parametrize("name", CONTROL_NAMES)
def test_control_names_rejected_all_casings_as_file_and_dir(name):
    for variant in _casings(name):
        # rejected as a bare leaf, nested leaf, and directory component
        with pytest.raises(ValidationError):
            validate_relative_path(variant)
        with pytest.raises(ValidationError):
            validate_relative_path(f"tests/{variant}/config")
        with pytest.raises(ValidationError):
            validate_dir_path(f"tests/{variant}")


def test_specific_mixed_case_control_names_rejected():
    for value in [
        ".Git",
        ".GIT",
        "tests/.Git/config",
        ".GitIgnore",
        "tests/.GITATTRIBUTES",
        ".GitModules",
    ]:
        with pytest.raises(ValidationError):
            validate_relative_path(value)


# -- rejection: unsafe forms stay rejected -------------------------------------

REJECTED_PATHS = [
    ".git",
    ".git/config",
    "tests/.git/config",
    "tests/.hidden/input.txt",
    "tests/..",
    "tests/./input.txt",
    "tests/name.",
    "tests/name ",
    "tests/C:",
    "tests\\input.py",
    ".gitignore",
    "tests/.gitattributes",
    ".gitmodules",
]


@pytest.mark.parametrize("path", REJECTED_PATHS)
def test_unsafe_paths_still_rejected(path):
    with pytest.raises(ValidationError):
        validate_relative_path(path)


@pytest.mark.parametrize("path", REJECTED_PATHS)
def test_reviewer_path_admission_rejects_unsafe(path):
    with pytest.raises(ValueError):
        admit_reviewer_path(path)


# -- case ids stay strict (no '+' and no leading dot) --------------------------


@pytest.mark.parametrize("case_id", [".hidden", "case+one"])
def test_case_ids_reject_dot_prefix_and_plus(case_id):
    with pytest.raises(ValidationError):
        validate_case_id(case_id)


def test_dot_leaf_is_a_path_but_never_a_case_id():
    # The exact distinction the split policy exists for: a dot-leaf is a valid
    # relative path component yet an invalid case id.
    assert validate_relative_path(".coveragerc") == ".coveragerc"
    with pytest.raises(ValidationError):
        validate_case_id(".coveragerc")
