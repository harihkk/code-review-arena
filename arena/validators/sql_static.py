"""Static checks for tenant-scoped SQL access."""

from __future__ import annotations

from arena.validators.base import (
    BaseValidator,
    ValidatorContext,
    ValidatorResult,
    read_expected_file,
)


class SQLHasTenantOrOwnerFilter(BaseValidator):
    name = "sql_has_tenant_or_owner_filter"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_file(context)
        lower = text.lower()
        scopes = [
            "tenant_id",
            "org_id",
            "organization_id",
            "team_id",
            "owner_id",
            "account_id",
        ]
        found = [scope for scope in scopes if scope in lower]
        passed = "where" in lower and bool(found)
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.98 if passed else 0.96,
            message=(
                "Document query contains an ownership or tenant predicate."
                if passed
                else "Document query filters by resource ID without ownership scope."
            ),
            evidence=[f"Scoped predicate references `{scope}`." for scope in found],
        )
