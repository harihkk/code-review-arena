"""Optional static validators for TypeScript benchmark cases."""

from __future__ import annotations

from arena.validators.base import (
    BaseValidator,
    ValidatorContext,
    ValidatorResult,
    read_expected_source,
)


class ReactUsesFunctionalStateUpdate(BaseValidator):
    name = "react_uses_functional_state_update"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        normalized = text.replace(" ", "")
        passed = "setMessages(previous=>[...previous,message])" in normalized or (
            "setMessages(" in text and "=>" in text and "...previous" in text
        )
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.9,
            message="State update uses the prior value function."
            if passed
            else "State update still closes over stale state.",
            evidence=["Functional state update found."] if passed else [],
        )


class GraphQLUsesBatchingOrDataLoader(BaseValidator):
    name = "graphql_uses_batching_or_dataloader"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        passed = "dataloader" in lower or "loadmany" in lower or "batch" in lower
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.85,
            message="Resolver uses batching semantics."
            if passed
            else "Resolver still performs per-item loading.",
            evidence=["Batch/DataLoader call found."] if passed else [],
        )
