"""Pack certification: is a benchmark case a real test of repair?

A trustworthy executable case must satisfy three gates:

- the buggy baseline (before/) FAILS the tests -- the bug is actually exercised;
- the reference solution (after/) PASSES the tests -- the intended fix works;
- mutants of the solution are killed -- the tests catch wrong code, not just the
  one reference fix (see arena.benchmark.mutation).

Cases without executable tests are reported as development-only: useful for
detection scoring, but not certifiable as execution-backed.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from arena.benchmark.case_loader import load_cases
from arena.benchmark.mutation import run_mutation_test
from arena.benchmark.solution import fixed_solution
from arena.core.models import BenchmarkCase
from arena.execution.test_executor import TestExecutionRequest, TestExecutionResult, TestExecutor


@dataclass
class CaseCertification:
    case_id: str
    executable: bool
    baseline_fails: bool | None = None
    reference_passes: bool | None = None
    mutant_total: int = 0
    mutant_kill_rate: float | None = None

    @property
    def certified(self) -> bool:
        return self.executable and self.baseline_fails is True and self.reference_passes is True


@dataclass
class PackCertification:
    pack: str
    cases: list[CaseCertification] = field(default_factory=list)

    @property
    def level(self) -> str:
        executable = [case for case in self.cases if case.executable]
        if executable and all(case.certified for case in executable):
            return "certified"
        return "development"


def _run_tests_in(
    case: BenchmarkCase,
    source_dir: Path | None,
    *,
    executor: TestExecutor,
    allow_local_execution: bool,
) -> TestExecutionResult | None:
    """Run the case's tests against a copy of ``source_dir`` plus the hidden tests."""
    if source_dir is None or not source_dir.is_dir() or not case.execution.test_command:
        return None
    assert case.case_dir is not None
    with tempfile.TemporaryDirectory(prefix=f"arena-certify-{case.id}-") as directory:
        workspace = Path(directory)
        shutil.copytree(source_dir, workspace, dirs_exist_ok=True)
        tests_dir = case.input.tests_dir
        if tests_dir and (case.case_dir / tests_dir).is_dir():
            shutil.copytree(case.case_dir / tests_dir, workspace / tests_dir, dirs_exist_ok=True)
        return executor.execute(
            TestExecutionRequest(
                case_id=case.id,
                workspace_path=workspace,
                test_command=case.execution.test_command,
                timeout_seconds=case.execution.timeout_seconds,
                docker_image=case.execution.docker_image,
                allow_local_execution=allow_local_execution,
            )
        )


def certify_case(
    case: BenchmarkCase,
    *,
    executor: TestExecutor | None = None,
    allow_local_execution: bool = False,
    mutation_limit: int = 20,
) -> CaseCertification:
    executor = executor or TestExecutor()
    if not case.execution.run_tests or not case.execution.test_command:
        return CaseCertification(case_id=case.id, executable=False)

    assert case.case_dir is not None
    # The buggy PR state (after/) must FAIL the tests: the bug is exercised.
    baseline = _run_tests_in(
        case,
        case.case_dir / case.input.after_dir,
        executor=executor,
        allow_local_execution=allow_local_execution,
    )
    # The corrected solution (after/ + reference.patch) must PASS the tests.
    with fixed_solution(case) as fixed:
        reference = _run_tests_in(
            case, fixed, executor=executor, allow_local_execution=allow_local_execution
        )
    mutation = run_mutation_test(
        case, executor=executor, allow_local_execution=allow_local_execution, limit=mutation_limit
    )
    return CaseCertification(
        case_id=case.id,
        executable=True,
        baseline_fails=(baseline.ran and not baseline.passed) if baseline else None,
        reference_passes=(reference.ran and reference.passed) if reference else None,
        mutant_total=mutation.total,
        mutant_kill_rate=mutation.kill_rate,
    )


def certify_pack(
    benchmark_dir: Path,
    *,
    allow_local_execution: bool = False,
    mutation_limit: int = 20,
) -> PackCertification:
    executor = TestExecutor()
    result = PackCertification(pack=benchmark_dir.name)
    for case in load_cases(benchmark_dir):
        result.cases.append(
            certify_case(
                case,
                executor=executor,
                allow_local_execution=allow_local_execution,
                mutation_limit=mutation_limit,
            )
        )
    return result
