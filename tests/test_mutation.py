"""Mutation testing: generator produces single-edit mutants; tests kill caught ones."""

from arena.benchmark.mutation import generate_mutants, run_mutation_test
from arena.core.models import BenchmarkCase


def test_generator_swaps_a_comparison():
    mutants = generate_mutants("def f(x):\n    return x >= 18\n")
    assert len(mutants) == 1
    assert "x < 18" in mutants[0].source
    assert "GtE -> Lt" in mutants[0].description


def test_generator_covers_boolop_arith_and_bool_constant():
    assert any("Or" in m.description for m in generate_mutants("y = a and b\n"))
    assert any("Sub" in m.description for m in generate_mutants("y = a + b\n"))
    assert any("False" in m.source for m in generate_mutants("flag = True\n"))


def test_generator_respects_limit_and_skips_unparseable():
    source = "\n".join(f"v{i} = a{i} == b{i}" for i in range(10))
    assert len(generate_mutants(source, limit=3)) == 3
    assert generate_mutants("def broken(:\n") == []


def test_generator_returns_nothing_without_mutation_sites():
    assert generate_mutants("x = 1\ny = 'hello'\n") == []


def _calc_case(tmp_path) -> BenchmarkCase:
    after = tmp_path / "after"
    after.mkdir()
    (after / "calc.py").write_text("def is_adult(age):\n    return age >= 18\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(
        "from calc import is_adult\n"
        "def test_adult():\n    assert is_adult(18) is True\n"
        "def test_minor():\n    assert is_adult(17) is False\n"
    )
    case = BenchmarkCase.model_validate(
        {
            "id": "calc",
            "title": "Age check",
            "category": "correctness",
            "severity": "high",
            "stack": ["python"],
            "description": "An adulthood check the tests pin tightly.",
            "input": {"after_dir": "after", "tests_dir": "tests"},
            "ground_truth": {
                "bugs": [
                    {
                        "summary": "age threshold",
                        "files": [{"path": "calc.py", "line_ranges": [{"start": 2, "end": 2}]}],
                        "concepts": ["correctness"],
                    }
                ]
            },
            "execution": {
                "run_tests": True,
                "test_command": "pytest -q tests",
                "timeout_seconds": 60,
            },
        }
    )
    case.case_dir = tmp_path
    return case


def test_run_mutation_test_kills_a_caught_mutant(tmp_path):
    case = _calc_case(tmp_path)
    result = run_mutation_test(case, allow_local_execution=True, limit=10)
    # The comparison mutant breaks the pinned behavior, so the tests kill it.
    assert result.total >= 1
    assert result.killed == result.total
    assert result.kill_rate == 1.0
