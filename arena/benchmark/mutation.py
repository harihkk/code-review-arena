"""Mutation testing: does a case's tests actually catch wrong repairs?

We take the correct solution and apply small, plausible-but-wrong edits (flip a
comparison, swap and/or, change an arithmetic operator, invert a boolean), then
run the case's tests against each mutant. A test suite that *fails* on a mutant
has "killed" it; one that still passes let a wrong repair through. A high
mutant-kill rate is evidence the case can tell a real fix from a lookalike,
which is what Repair Confidence is built on.
"""

from __future__ import annotations

import ast
import copy
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from arena.benchmark.solution import fixed_solution
from arena.core.models import BenchmarkCase
from arena.execution.test_executor import TestExecutionRequest, TestExecutor

# Plain type->type maps; ast op subclasses don't unify cleanly under stricter
# generic annotations, and the lookups are guarded by isinstance/type checks.
_COMPARE_SWAP: dict[type, type] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    # Membership checks drive dedup/allowlist/citation-validation fixes; flipping
    # them is exactly the lookalike a sharp test suite must reject.
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}
_BOOLOP_SWAP: dict[type, type] = {ast.And: ast.Or, ast.Or: ast.And}
_ARITH_SWAP: dict[type, type] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
}


@dataclass
class Mutant:
    description: str
    source: str


@dataclass
class MutationResult:
    total: int
    killed: int
    survivors: list[str] = field(default_factory=list)

    @property
    def kill_rate(self) -> float | None:
        return self.killed / self.total if self.total else None


def _eligible(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    """Mutation sites in a stable walk order (so index N is the same per run)."""
    sites: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and type(node.ops[0]) in _COMPARE_SWAP
        ):
            sites.append(("compare", node))
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOLOP_SWAP:
            sites.append(("boolop", node))
        elif isinstance(node, ast.BinOp) and type(node.op) in _ARITH_SWAP:
            sites.append(("arith", node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            sites.append(("const", node))
    return sites


def _apply(kind: str, node: ast.AST) -> str:
    if kind == "compare":
        assert isinstance(node, ast.Compare)
        old_cmp = type(node.ops[0])
        new_cmp = _COMPARE_SWAP[old_cmp]
        node.ops = [new_cmp()]
        return f"compare {old_cmp.__name__} -> {new_cmp.__name__}"
    if kind == "boolop":
        assert isinstance(node, ast.BoolOp)
        old_bool = type(node.op)
        new_bool = _BOOLOP_SWAP[old_bool]
        node.op = new_bool()
        return f"boolop {old_bool.__name__} -> {new_bool.__name__}"
    if kind == "arith":
        assert isinstance(node, ast.BinOp)
        old_arith = type(node.op)
        new_arith = _ARITH_SWAP[old_arith]
        node.op = new_arith()
        return f"arith {old_arith.__name__} -> {new_arith.__name__}"
    assert isinstance(node, ast.Constant)
    node.value = not node.value
    return f"const bool -> {node.value}"


def generate_mutants(source: str, *, limit: int = 25) -> list[Mutant]:
    """Produce up to ``limit`` single-edit mutants of ``source``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    site_count = len(_eligible(tree))
    mutants: list[Mutant] = []
    for index in range(min(site_count, limit)):
        clone = copy.deepcopy(tree)
        kind, node = _eligible(clone)[index]
        description = _apply(kind, node)
        try:
            mutated = ast.unparse(clone)
        except Exception:  # noqa: BLE001 - unparse can fail on odd trees; skip those.
            continue
        if mutated.strip() and mutated != source:
            mutants.append(Mutant(description=description, source=mutated))
    return mutants


def run_mutation_test(
    case: BenchmarkCase,
    *,
    executor: TestExecutor | None = None,
    allow_local_execution: bool = False,
    limit: int = 20,
) -> MutationResult:
    """Mutate the corrected solution's bug file and count how many mutants die.

    Mutants come from the *fixed* solution (after/ + reference.patch), which the
    tests pass. A mutant is "killed" when the tests then fail on it; one that
    still passes is a survivor the tests did not catch.
    """
    assert case.case_dir is not None
    executor = executor or TestExecutor()
    bug_path = case.ground_truth.primary_bug.files[0].path
    tests_dir = case.input.tests_dir

    killed = 0
    evaluated = 0
    survivors: list[str] = []
    with fixed_solution(case) as fixed:
        if fixed is None or not (fixed / bug_path).is_file():
            return MutationResult(total=0, killed=0)
        mutants = generate_mutants((fixed / bug_path).read_text(encoding="utf-8"), limit=limit)
        for mutant in mutants:
            with tempfile.TemporaryDirectory(prefix=f"arena-mut-{case.id}-") as directory:
                workspace = Path(directory)
                shutil.copytree(fixed, workspace, dirs_exist_ok=True)
                (workspace / bug_path).write_text(mutant.source, encoding="utf-8")
                if tests_dir and (case.case_dir / tests_dir).is_dir():
                    shutil.copytree(
                        case.case_dir / tests_dir, workspace / tests_dir, dirs_exist_ok=True
                    )
                result = executor.execute(
                    TestExecutionRequest(
                        case_id=case.id,
                        workspace_path=workspace,
                        test_command=case.execution.test_command or "pytest -q",
                        timeout_seconds=case.execution.timeout_seconds,
                        docker_image=case.execution.docker_image,
                        allow_local_execution=allow_local_execution,
                    )
                )
            if not result.ran:
                # The backend was unavailable for this mutant; it is inconclusive,
                # not a survivor. Counting it as survived would report kill_rate=0
                # ("the tests are weak") when really nothing ran.
                continue
            evaluated += 1
            if not result.passed:
                killed += 1
            else:
                survivors.append(mutant.description)
    return MutationResult(total=evaluated, killed=killed, survivors=survivors)
