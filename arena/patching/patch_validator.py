"""Combine patch, execution and structural evidence into one validation record."""

from __future__ import annotations

from arena.execution.test_executor import TestExecutionResult
from arena.patching.patch_models import PatchApplyResult, PatchValidationResult
from arena.validators.base import ValidatorResult


def build_patch_validation(
    patch: PatchApplyResult,
    tests: TestExecutionResult | None,
    validators: list[ValidatorResult],
) -> PatchValidationResult:
    return PatchValidationResult(
        patch_provided=bool(patch.patch_text.strip()),
        patch_applied=patch.applied,
        tests_passed=tests.passed if tests and tests.ran else None,
        structural_validation_passed=(
            all(item.passed for item in validators) if validators else None
        ),
        validators=validators,
        error=patch.error,
    )
