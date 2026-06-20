"""Adversarial and property-based tests for the strict pack path/id schema boundary."""

import copy
import json

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from arena.benchmark.case_loader import load_cases
from arena.core.errors import ValidationError
from arena.core.models import (
    AcceptableFinding,
    BenchmarkCase,
    CaseInput,
    CaseManifest,
    GroundTruthFile,
    ValidationConfig,
)
from arena.patching.patch_applier import PatchApplier
from arena.patching.patch_models import PatchApplyRequest
from arena.security.paths import (
    _WINDOWS_RESERVED,
    SafeRelativePath,
    _relative_path_error,
    assert_safe_delete_target,
    resolve_under,
    validate_case_id,
    validate_relative_path,
)

# (label, value) adversarial relative paths the SafeRelativePath policy must reject.
UNSAFE_RELATIVE_PATHS = [
    ("empty", ""),
    ("absolute_posix", "/etc/passwd"),
    ("traversal", "../escape"),
    ("interior_traversal", "a/../b"),
    ("dot_component", "a/./b"),
    ("empty_component", "a//b"),
    ("repeated_separators", "a///b"),
    ("leading_slash", "/a"),
    ("trailing_slash", "a/"),
    ("windows_drive", "C:\\x"),
    ("unc", "\\\\server\\share"),
    ("backslash", "a\\b"),
    ("colon", "a:b"),
    ("nul", "a\x00b"),
    ("newline", "a\nb"),
    ("space", "a b"),
    ("non_ascii", "caf\u00e9.py"),
    ("zero_width", "a\u200db"),
    ("fullwidth_solidus", "full\uff0fwidth"),
    ("trailing_dot", "foo."),
    ("trailing_space", "foo "),
    ("windows_con", "con"),
    ("windows_con_mixed_case", "CoN"),
    ("windows_nul_with_ext", "NUL.txt"),
    ("windows_com1", "COM1"),
    ("windows_reserved_nested", "src/aux/x.py"),
    ("too_long_component", "a" * 256),
    # Dot-prefixed components are omitted by the current pack checksum, so they
    # are rejected until Phase 1C snapshot hashing covers every regular file.
    ("dot_hidden", ".hidden"),
    ("dot_hidden_file", ".hidden/file.py"),
    ("nested_dot_hidden", "src/.hidden"),
    ("nested_dot_hidden_file", "src/.hidden/file.py"),
    ("bare_dot", "."),
    ("bare_dotdot", ".."),
]

VALID_CASE = {
    "id": "case_001",
    "title": "t",
    "category": "correctness",
    "severity": "high",
    "stack": ["python"],
    "description": "d",
    "input": {
        "diff": "pr.diff",
        "before_dir": "before",
        "after_dir": "after",
        "tests_dir": "tests",
    },
    "ground_truth": {
        "bugs": [
            {
                "summary": "b",
                "files": [{"path": "app.py", "line_ranges": [{"start": 1, "end": 1}]}],
                "concepts": ["x"],
            }
        ]
    },
    "validation": {"protected_paths": ["tests"]},
}


def _gt(path):
    return GroundTruthFile(path=path, line_ranges=[{"start": 1, "end": 1}])


@pytest.mark.parametrize(
    "label,value", UNSAFE_RELATIVE_PATHS, ids=[p[0] for p in UNSAFE_RELATIVE_PATHS]
)
def test_safe_relative_path_rejects_unsafe_inputs(label, value):
    # The domain wrapper raises Arena's ValidationError (used at I/O boundaries)...
    with pytest.raises(ValidationError):
        validate_relative_path(value)
    # ...and the model field raises Pydantic's ValidationError (collected per field).
    with pytest.raises(PydanticValidationError):
        _gt(value)


def test_safe_relative_path_accepts_legitimate_paths():
    for value in [
        "app/pricing.py",
        "before",
        "pr.diff",
        "tests/test_x.py",
        "a-b/c_d.py",
    ]:
        assert validate_relative_path(value) == value
        assert _gt(value).path == value


# -- Pydantic error integration ------------------------------------------------


@pytest.mark.parametrize(
    "loc,mutate",
    [
        ("input.after_dir", lambda d: d["input"].__setitem__("after_dir", "../x")),
        (
            "ground_truth.bugs.0.files.0.path",
            lambda d: d["ground_truth"]["bugs"][0]["files"][0].__setitem__("path", "../x"),
        ),
        (
            "validation.protected_paths.0",
            lambda d: d["validation"].__setitem__("protected_paths", ["../x"]),
        ),
    ],
)
def test_invalid_nested_path_is_a_pydantic_error_at_the_right_location(loc, mutate):
    doc = copy.deepcopy(VALID_CASE)
    mutate(doc)
    with pytest.raises(PydanticValidationError) as exc_info:
        BenchmarkCase.model_validate(doc)
    locations = {".".join(str(p) for p in error["loc"]) for error in exc_info.value.errors()}
    assert loc in locations
    # It must NOT escape as the Arena domain exception from inside a model validator.
    assert not isinstance(exc_info.value, ValidationError)


# -- SafeCaseId at the schema boundary -----------------------------------------


def test_case_id_is_enforced_on_models_not_just_load():
    with pytest.raises(PydanticValidationError):
        BenchmarkCase.model_validate({**copy.deepcopy(VALID_CASE), "id": "../escape"})
    with pytest.raises(PydanticValidationError):
        CaseManifest(version="v", name="n", cases=["ok", "a/b"])
    assert BenchmarkCase.model_validate(copy.deepcopy(VALID_CASE)).id == "case_001"


def test_manifest_rejects_duplicate_case_ids():
    with pytest.raises(PydanticValidationError):
        CaseManifest(version="v", name="n", cases=["a", "b", "a"])
    assert CaseManifest(version="v", name="n", cases=["a", "b"]).cases == ["a", "b"]


# -- list / optional / default / serialization surfaces ------------------------


def test_every_pack_path_field_is_contained():
    with pytest.raises(PydanticValidationError):
        CaseInput(after_dir="../../etc")
    with pytest.raises(PydanticValidationError):
        CaseInput(tests_dir="/abs/tests")
    with pytest.raises(PydanticValidationError):
        ValidationConfig(protected_paths=["ok/path", "../escape"])
    assert CaseInput(after_dir="after", tests_dir="tests").after_dir == "after"


def test_optional_paths_accept_none():
    assert AcceptableFinding(path=None, concepts=["x"]).path is None
    assert CaseInput(tests_dir=None).tests_dir is None


def test_default_path_values_are_valid():
    defaults = CaseInput()
    for value in (defaults.diff, defaults.before_dir, defaults.after_dir, defaults.tests_dir):
        assert _relative_path_error(value) is None


def test_type_adapter_validates_and_emits_json_schema():
    adapter = TypeAdapter(SafeRelativePath)
    assert adapter.validate_python("app/x.py") == "app/x.py"
    with pytest.raises(PydanticValidationError):
        adapter.validate_python("../x")
    assert adapter.json_schema()["type"] == "string"


def test_json_and_yaml_loading_reject_bad_paths_and_round_trip():
    assert CaseInput.model_validate(json.loads('{"after_dir": "app/x"}')).after_dir == "app/x"
    with pytest.raises(PydanticValidationError):
        CaseInput.model_validate(json.loads('{"after_dir": "../escape"}'))
    with pytest.raises(PydanticValidationError):
        CaseInput.model_validate(yaml.safe_load("after_dir: '../escape'"))
    case = CaseInput(after_dir="after", tests_dir="tests")
    assert CaseInput.model_validate(case.model_dump(mode="json")).after_dir == "after"


# -- property-based suite ------------------------------------------------------

_PATH_ALPHABET = "abcdefABCDEF0123456789_-."


def _valid_component(text: str) -> bool:
    return (
        bool(text)
        and text not in {".", ".."}
        and not text.startswith(".")
        and not text.endswith((".", " "))
        and text.split(".")[0].upper() not in _WINDOWS_RESERVED
        and len(text) <= 255
    )


@given(
    st.lists(
        st.text(alphabet=_PATH_ALPHABET, min_size=1, max_size=12).filter(_valid_component),
        min_size=1,
        max_size=5,
    )
)
def test_generated_portable_paths_are_accepted(parts):
    path = "/".join(parts)
    assert validate_relative_path(path) == path
    assert _gt(path).path == path


@given(st.text(min_size=1, max_size=40))
def test_any_string_outside_the_ascii_profile_is_rejected(text):
    if any(ch not in (_PATH_ALPHABET + "ghijklmnopqrstuvwxyzGHIJKLMNOPQRSTUVWXYZ/") for ch in text):
        assert _relative_path_error(text) is not None


@given(st.lists(st.sampled_from(["a", "b", ".", "..", ""]), min_size=1, max_size=5))
def test_any_dot_or_empty_component_is_rejected(parts):
    if any(part in {"", ".", ".."} for part in parts):
        assert _relative_path_error("/".join(parts)) is not None


# -- case id and containment (retained) ----------------------------------------


def test_valid_case_id_accepted():
    # Real slugs, and valid names that merely contain a reserved substring.
    for value in [
        "money_discount_rounding_001",
        "2026-06-19_15-32-06",
        "null_handler",
        "com_port_check",
        "console_logging",
        "auxiliary",
    ]:
        assert validate_case_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "/tmp/example",
        "..",
        "../../example",
        "a/b",
        "",
        "C:\\example",
        r"\\server\share",
        "NUL",
        "nul",
        "nul.txt",
        "COM1",
        "lpt9.log",
        "AUX.py",
        "CoN",
        "case.",
        "case ",
        "caf\u00e9",
        "a" * 256,
        ".hidden_case",
        "-case",
        "_case",
    ],
)
def test_unsafe_case_ids_rejected(value):
    # A case id is one filesystem component, so it gets the full portable policy:
    # reserved device names (even with extensions, any case), trailing dot/space,
    # non-ASCII, over-length, and anything that is not a single component.
    with pytest.raises(ValidationError):
        validate_case_id(value)


def test_case_id_and_relative_path_share_one_component_policy():
    # The reserved-name and trailing-dot rules hold identically whether the value
    # arrives as a single-component relative path or as a case id.
    for value in ["NUL.txt", "COM1", "case."]:
        with pytest.raises(ValidationError):
            validate_relative_path(value)
        with pytest.raises(ValidationError):
            validate_case_id(value)


def test_after_dir_cannot_escape_case(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    with pytest.raises(ValidationError):
        resolve_under(case_dir, "../../after")
    assert resolve_under(case_dir, "after") == (case_dir / "after").resolve()


def test_resolve_under_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError):
        resolve_under(root, "link/secret")


def test_safe_delete_refuses_root_and_outside_and_symlink(tmp_path):
    root = tmp_path / "workspaces"
    root.mkdir()
    (tmp_path / "elsewhere").mkdir()
    with pytest.raises(ValidationError):
        assert_safe_delete_target(root, root)
    with pytest.raises(ValidationError):
        assert_safe_delete_target(root, tmp_path / "elsewhere")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "case"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValidationError):
        assert_safe_delete_target(root, link)
    (root / "case_001").mkdir()
    assert_safe_delete_target(root, root / "case_001")  # contained child is allowed


def test_patch_applier_rejects_unsafe_case_id(tmp_path):
    applier = PatchApplier(tmp_path / "runs")
    request = PatchApplyRequest(
        case_id="../../../etc",
        source_dir=tmp_path / "src",
        patch_text="",
        run_id="run1",
    )
    with pytest.raises(ValidationError):
        applier.apply(request)


# -- case identity invariant at pack load --------------------------------------


def _write_min_pack(root, *, manifest_cases, case_dirs):
    root.mkdir(parents=True)
    (root / "manifest.yaml").write_text(
        yaml.safe_dump({"version": "v", "name": "n", "cases": manifest_cases})
    )
    for dir_name, case_id in case_dirs.items():
        case_dir = root / dir_name
        case_dir.mkdir(parents=True)
        case = copy.deepcopy(VALID_CASE)
        case["id"] = case_id
        (case_dir / "case.yaml").write_text(yaml.safe_dump(case))
    return root


def test_load_cases_enforces_manifest_dir_id_identity(tmp_path):
    ok = _write_min_pack(
        tmp_path / "ok", manifest_cases=["case_001"], case_dirs={"case_001": "case_001"}
    )
    assert [c.id for c in load_cases(ok)] == ["case_001"]
    # case.yaml id disagrees with the directory/manifest id.
    bad = _write_min_pack(
        tmp_path / "bad", manifest_cases=["case_001"], case_dirs={"case_001": "different_id"}
    )
    with pytest.raises(ValidationError, match="mismatch"):
        load_cases(bad)


def test_load_cases_rejects_case_insensitive_id_collision(tmp_path):
    pack = tmp_path / "collide"
    pack.mkdir()
    (pack / "manifest.yaml").write_text(
        yaml.safe_dump({"version": "v", "name": "n", "cases": ["CaseA", "casea"]})
    )
    with pytest.raises(ValidationError, match="collide"):
        load_cases(pack)


def test_load_cases_rejects_duplicate_manifest_ids(tmp_path):
    pack = tmp_path / "dup"
    pack.mkdir()
    (pack / "manifest.yaml").write_text(
        yaml.safe_dump({"version": "v", "name": "n", "cases": ["dup", "dup"]})
    )
    with pytest.raises(ValidationError):
        load_cases(pack)


# -- pack-level: fail closed on content the checksum cannot see ----------------


def test_load_and_validate_pack_fails_closed_on_unhashable_content(tmp_path):
    import shutil

    from arena.benchmark.dataset_validator import load_and_validate_pack

    pack = tmp_path / "pack"
    shutil.copytree("benchmark_sets/audit_v2", pack)
    # The clean copy admits.
    load_and_validate_pack(pack)
    # A hidden regular file under a case is invisible to pack_checksum, so it
    # could be swapped without changing the digest: admission must fail closed.
    (pack / "money_discount_rounding_001" / ".secret.py").write_text("X = 1\n")
    with pytest.raises(ValidationError, match="checksum"):
        load_and_validate_pack(pack)


def test_load_and_validate_pack_fails_closed_on_pycache(tmp_path):
    import shutil

    from arena.benchmark.dataset_validator import load_and_validate_pack

    pack = tmp_path / "pack"
    shutil.copytree("benchmark_sets/audit_v2", pack)
    cache = pack / "money_discount_rounding_001" / "__pycache__"
    cache.mkdir()
    (cache / "x.cpython-311.pyc").write_bytes(b"\x00\x01")
    with pytest.raises(ValidationError, match="checksum"):
        load_and_validate_pack(pack)
