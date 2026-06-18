"""Pack certification: baseline-fails, reference-passes, and mutant-kill gates.

Convention under test: after/ holds the buggy PR state, reference.patch is the
fix applied on top of it, and the hidden tests pin the correct behavior.
"""

from pathlib import Path

from arena.benchmark.certify import certify_pack

# A bug file with a tightly tested fix plus an untested helper. The helper's
# comparison and boolean mutants survive (no test exercises them), dragging the
# kill rate below CERTIFIED_KILL_RATE even though the real fix is caught.
WEAK_AFTER = (
    "def is_adult(age):\n"
    "    return age > 18\n"
    "\n"
    "def unused(value):\n"
    "    return value > 0 and value < 100\n"
)
WEAK_REFERENCE_PATCH = (
    "--- a/calc.py\n+++ b/calc.py\n@@ -1,3 +1,3 @@\n"
    " def is_adult(age):\n-    return age > 18\n+    return age >= 18\n \n"
)

CASE_YAML = """id: calc_case
title: Age check
category: correctness
severity: high
stack: [python]
description: An adulthood check the tests pin tightly.
input: {diff: pr.diff, before_dir: before, after_dir: after, tests_dir: tests}
ground_truth:
  bugs:
    - summary: age threshold
      files: [{path: calc.py, line_ranges: [{start: 2, end: 2}]}]
      concepts: [correctness]
execution: {run_tests: true, test_command: 'pytest -q tests', timeout_seconds: 60}
"""

TESTS = (
    "from calc import is_adult\n"
    "def test_adult():\n    assert is_adult(18) is True\n"
    "def test_minor():\n    assert is_adult(17) is False\n"
)

# Fixes the buggy `> 18` in after/calc.py to the correct `>= 18`.
REFERENCE_PATCH = (
    "--- a/calc.py\n+++ b/calc.py\n@@ -1,2 +1,2 @@\n"
    " def is_adult(age):\n-    return age > 18\n+    return age >= 18\n"
)


def _build_pack(root: Path, *, after: str, reference_patch: str | None) -> Path:
    pack = root / "pack"
    case = pack / "calc_case"
    (case / "before").mkdir(parents=True)
    (case / "after").mkdir(parents=True)
    (case / "tests").mkdir(parents=True)
    (pack / "manifest.yaml").write_text("version: certify_v1\nname: certify\ncases: [calc_case]\n")
    (case / "before" / "calc.py").write_text("def is_adult(age):\n    return age >= 18\n")
    (case / "after" / "calc.py").write_text(after)
    (case / "pr.diff").write_text("--- a/calc.py\n+++ b/calc.py\n@@\n-x\n+y\n")
    (case / "tests" / "test_calc.py").write_text(TESTS)
    (case / "case.yaml").write_text(CASE_YAML)
    if reference_patch is not None:
        (case / "reference.patch").write_text(reference_patch)
    return pack


def test_certify_pack_certifies_a_well_formed_case(tmp_path):
    # after/ is buggy (> 18); reference.patch corrects it to >= 18.
    pack = _build_pack(
        tmp_path,
        after="def is_adult(age):\n    return age > 18\n",
        reference_patch=REFERENCE_PATCH,
    )
    report = certify_pack(pack, allow_local_execution=True)
    assert report.level == "certified"
    case = report.cases[0]
    assert case.executable
    assert case.baseline_fails is True  # the buggy PR state is caught
    assert case.reference_passes is True  # the reference fix works
    assert case.certified
    assert case.mutant_kill_rate == 1.0  # the comparison mutant is killed


def test_certify_flags_a_case_whose_baseline_does_not_fail(tmp_path):
    # after/ is already correct and there is no fix to apply: the bug is not
    # exercised, so the case is not certifiable.
    pack = _build_pack(
        tmp_path,
        after="def is_adult(age):\n    return age >= 18\n",
        reference_patch=None,
    )
    report = certify_pack(pack, allow_local_execution=True)
    case = report.cases[0]
    assert case.baseline_fails is False
    assert case.reference_passes is True
    assert not case.certified
    assert report.level == "development"


def test_determinism_gate_promotes_a_stable_case_to_verified(tmp_path):
    pack = _build_pack(
        tmp_path,
        after="def is_adult(age):\n    return age > 18\n",
        reference_patch=REFERENCE_PATCH,
    )
    report = certify_pack(pack, allow_local_execution=True, determinism_runs=3)
    case = report.cases[0]
    assert case.certified
    assert case.deterministic is True
    assert case.determinism_runs == 3
    assert case.level == "verified"
    assert report.level == "verified"


def test_certified_case_without_determinism_check_tops_out_at_certified(tmp_path):
    pack = _build_pack(
        tmp_path,
        after="def is_adult(age):\n    return age > 18\n",
        reference_patch=REFERENCE_PATCH,
    )
    report = certify_pack(pack, allow_local_execution=True)  # determinism_runs defaults to 1
    case = report.cases[0]
    assert case.certified
    assert case.deterministic is None
    assert case.level == "certified"


def test_weak_tests_fail_the_mutation_gate(tmp_path):
    # The fix is caught, but most of the file's mutants survive, so the suite is
    # not sharp enough to certify the case as a real test of repair.
    pack = _build_pack(tmp_path, after=WEAK_AFTER, reference_patch=WEAK_REFERENCE_PATCH)
    report = certify_pack(pack, allow_local_execution=True)
    case = report.cases[0]
    assert case.baseline_fails is True
    assert case.reference_passes is True
    assert case.mutant_kill_rate is not None and case.mutant_kill_rate < 0.5
    assert not case.mutation_adequate
    assert not case.certified
    assert case.level == "development"


def test_case_without_executable_tests_is_draft(tmp_path):
    pack = _build_pack(
        tmp_path,
        after="def is_adult(age):\n    return age > 18\n",
        reference_patch=REFERENCE_PATCH,
    )
    # Strip the execution block so the case has no runnable tests.
    case_yaml = (pack / "calc_case" / "case.yaml").read_text()
    case_yaml = case_yaml.replace(
        "execution: {run_tests: true, test_command: 'pytest -q tests', timeout_seconds: 60}\n",
        "",
    )
    (pack / "calc_case" / "case.yaml").write_text(case_yaml)
    report = certify_pack(pack, allow_local_execution=True)
    case = report.cases[0]
    assert not case.executable
    assert case.level == "draft"
    assert report.level == "draft"
