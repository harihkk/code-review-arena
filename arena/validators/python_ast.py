"""Tolerant Python structural validators for seeded benchmark defects."""

from __future__ import annotations

import ast
import re

from arena.validators.base import (
    BaseValidator,
    ValidatorContext,
    ValidatorResult,
    read_expected_source,
)


class FastAPIRequiresAdminAuthorization(BaseValidator):
    name = "fastapi_requires_admin_authorization"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        evidence: list[str] = []
        try:
            tree = ast.parse(text)
            rendered = ast.dump(tree).lower()
        except SyntaxError:
            rendered = lower
        dependency = any(
            marker in lower.replace(" ", "")
            for marker in ["depends(require_admin)", "depends(admin_required)"]
        )
        helper = bool(
            re.search(
                r"(?<!def )\b(?:require_permission|check_admin_permission|authorize_admin)"
                r"\s*\(",
                lower,
            )
        )
        role_check = "is_admin" in lower or bool(
            re.search(
                r"(?:role|permissions?).{0,50}(?:==|!=|\bin\b).{0,30}"
                r"(?:admin|administrator)",
                lower,
                flags=re.DOTALL,
            )
        )
        compact = lower.replace(" ", "")
        denied = (
            "status_code=403" in compact
            or ("forbidden" in lower and role_check)
            or ("returnnone" in compact and role_check)
        )
        if dependency:
            evidence.append("Admin authorization dependency is attached to the route.")
        if helper and not dependency:
            evidence.append("Route invokes a helper with admin or permission semantics.")
        if role_check and denied:
            evidence.append("Route checks privilege and rejects unauthorized access.")
        passed = dependency or helper or (role_check and denied)
        if "functiondef" in rendered and passed:
            evidence.append("Patched module parses as a Python route implementation.")
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.92 if passed else 0.9,
            message=(
                "A credible administrator authorization path was found."
                if passed
                else "The admin route still lacks a credible authorization guard."
            ),
            evidence=evidence,
        )


class KafkaIdempotencyGuard(BaseValidator):
    name = "kafka_idempotency_guard"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        key_positions = [
            lower.find(token) for token in ["event_id", "message_id", "idempotency_key"]
        ]
        has_key = any(position >= 0 for position in key_positions)
        mutation_positions = [
            position
            for position in [lower.find(".credit("), lower.find(".update("), lower.find(".apply(")]
            if position >= 0
        ]
        mutation = min(mutation_positions) if mutation_positions else -1
        guard_markers = ["processed_event", "processed_message", "idempotency", "already_processed"]
        guard = min((lower.find(token) for token in guard_markers if token in lower), default=-1)
        record = max(
            (
                lower.rfind(token)
                for token in ["add(", "insert", "save(", "record"]
                if token in lower
            ),
            default=-1,
        )
        conditional = "if " in lower or "exists" in lower or "contains" in lower
        passed = (
            has_key and mutation >= 0 and guard >= 0 and conditional and guard < mutation < record
        )
        evidence = []
        if has_key:
            evidence.append("A unique event/message identifier is referenced.")
        if guard >= 0 and mutation >= 0 and guard < mutation:
            evidence.append("Processed-event state is checked before mutation.")
        if record > mutation >= 0:
            evidence.append("Processed-event state is recorded after mutation.")
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.94 if passed else 0.88,
            message=(
                "Idempotency guard wraps the state mutation."
                if passed
                else "No complete check-then-record idempotency guard surrounds the mutation."
            ),
            evidence=evidence,
        )


class FastAPITenantAdminAuthorization(BaseValidator):
    name = "fastapi_tenant_admin_authorization"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        evidence: list[str] = []
        tenant_dependency = any(
            marker in lower.replace(" ", "")
            for marker in [
                "depends(require_tenant_admin)",
                "depends(require_admin_for_tenant)",
                "depends(tenant_admin_required)",
            ]
        )
        tenant_helper = bool(
            re.search(
                r"\b(?:require_tenant_admin|require_admin_for_tenant|authorize_tenant_admin)\s*\(",
                lower,
            )
        )
        role_check = bool(
            re.search(
                r"(?:has_role|is_admin|role).{0,80}(?:tenant|org|organization)",
                lower,
                flags=re.DOTALL,
            )
        )
        tenant_guard = bool(
            re.search(
                r"tenant_id.{0,40}(?:!=|==|in\b)|(?:!=|==).{0,40}tenant_id",
                lower,
                flags=re.DOTALL,
            )
        )
        denied = "status_code=403" in lower.replace(" ", "") or (
            "forbidden" in lower and (role_check or tenant_guard)
        )
        passed = tenant_dependency or tenant_helper or (role_check and tenant_guard and denied)
        if tenant_dependency:
            evidence.append("Route depends on a tenant-scoped admin guard.")
        if tenant_helper:
            evidence.append("Route invokes a tenant admin authorization helper.")
        if role_check and tenant_guard:
            evidence.append("Route checks tenant-scoped administrator privilege.")
        auth_only = "depends(get_current_user)" in lower.replace(" ", "") and not passed
        if auth_only:
            passed = False
            evidence.append("Route only checks authentication, not tenant admin privilege.")
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.93 if passed else 0.9,
            message=(
                "Tenant-scoped administrator authorization is enforced."
                if passed
                else "Tenant admin route still lacks tenant-scoped administrator enforcement."
            ),
            evidence=evidence,
        )


class AsyncUpdateAtomicityGuard(BaseValidator):
    name = "async_update_atomicity_guard"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        evidence: list[str] = []
        lock_guard = "asyncio.lock" in lower and "async with" in lower
        transaction = any(term in lower for term in ["begin_transaction", "transaction", "atomic"])
        versioned = any(term in lower for term in ["version", "compare_and_swap", "cas("])
        unguarded = bool(
            re.search(
                r"current\s*=\s*self\.balance[\s\S]{0,120}self\.balance\s*=\s*current",
                lower,
            )
        )
        passed = lock_guard or transaction or versioned
        if lock_guard:
            evidence.append("Concurrent updates are guarded with asyncio.Lock.")
        if transaction:
            evidence.append("Updates run inside a transaction or atomic abstraction.")
        if versioned:
            evidence.append("Updates use a version or compare-and-swap check.")
        if unguarded and not passed:
            evidence.append("Read-modify-write balance update remains unguarded.")
        return ValidatorResult(
            name=self.name,
            passed=passed and not (unguarded and not lock_guard),
            confidence=0.94 if passed else 0.9,
            message=(
                "Concurrent balance mutation is protected."
                if passed
                else "Balance updates remain vulnerable to lost concurrent writes."
            ),
            evidence=evidence,
        )


class TenantScopedIdempotencyKey(BaseValidator):
    name = "tenant_scoped_idempotency_key"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        expression = lower
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                lookup_names = {"lookup", "store", "get", "set"}
                if isinstance(node, ast.FunctionDef) and node.name in lookup_names:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Subscript) and sub.value is not None:
                            expression += " " + ast.unparse(sub.value).lower()
                        if isinstance(sub, ast.Tuple):
                            expression += " " + ast.unparse(sub).lower()
        except SyntaxError:
            pass
        tuple_key = bool(
            re.search(r"\.get\(\s*\([^)]*,\s*key\s*\)", expression)
            or re.search(r"\[\s*\([^)]*,\s*key\s*\)\s*\]", expression)
            or re.search(r"\[\s*\(\s*(?:tenant|org|account|workspace)", expression)
        )
        global_only = bool(
            re.search(r"\.get\(\s*key\s*\)", expression)
            or re.search(r"_records\[\s*key\s*\]", expression)
        )
        passed = tuple_key and not global_only
        evidence = []
        if tuple_key:
            evidence.append(
                "Idempotency lookup/storage includes tenant or account scope with the key."
            )
        if global_only:
            evidence.append("Idempotency storage still appears globally keyed.")
            passed = False
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.95 if passed else 0.9,
            message=(
                "Idempotency keys are scoped per tenant or account."
                if passed
                else "Idempotency storage is not scoped by tenant or account."
            ),
            evidence=evidence,
        )


class RedisCacheKeyHasTenantScope(BaseValidator):
    name = "redis_cache_key_has_tenant_scope"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        expression = ""
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "cache_key":
                    returned = next(
                        (item for item in ast.walk(node) if isinstance(item, ast.Return)), None
                    )
                    expression = (
                        ast.unparse(returned.value).lower()
                        if returned is not None and returned.value is not None
                        else ""
                    )
                    break
        except SyntaxError:
            expression = text.lower()
        tenant_terms = ["tenant_id", "org_id", "organization_id", "workspace_id", "account_id"]
        dimensions = ["user_id", "query", "filter"]
        tenant = next((term for term in tenant_terms if term in expression), None)
        included = [term for term in dimensions if term in expression]
        passed = tenant is not None and bool(included)
        evidence = (
            [f"Cache key includes tenant scope `{tenant}` and dimension(s) {', '.join(included)}."]
            if passed
            else []
        )
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.97 if passed else 0.94,
            message=(
                "Cache key contains tenant scope and request/user dimensions."
                if passed
                else "Cache key remains insufficiently scoped for tenant isolation."
            ),
            evidence=evidence,
        )


class JWTAudienceIssuerValidated(BaseValidator):
    name = "jwt_audience_issuer_validated"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        # Match inside executable function bodies only: a leftover import of
        # EXPECTED_AUDIENCE/EXPECTED_ISSUER must not satisfy the check.
        lower = text.lower()
        try:
            tree = ast.parse(text)
            bodies = [
                statement
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                for statement in node.body
            ]
            if bodies:
                lower = "\n".join(ast.unparse(statement) for statement in bodies).lower()
        except SyntaxError:
            pass
        evidence: list[str] = []
        audience = any(
            marker in lower for marker in ['"aud"', "'aud'", "audience", "expected_audience"]
        )
        issuer = any(marker in lower for marker in ['"iss"', "'iss'", "issuer", "expected_issuer"])
        signature_only = bool(
            re.search(
                r"return\s+bool\([^)]*signature",
                lower,
            )
            and not audience
            and not issuer
        )
        passed = audience and issuer and not signature_only
        if audience:
            evidence.append("Token verification checks audience.")
        if issuer:
            evidence.append("Token verification checks issuer.")
        if signature_only:
            evidence.append("Verifier only checks signature validity.")
            passed = False
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.94 if passed else 0.9,
            message=(
                "JWT verification validates audience and issuer."
                if passed
                else "JWT verification still omits audience or issuer checks."
            ),
            evidence=evidence,
        )


class EventVersionMonotonicGuard(BaseValidator):
    name = "event_version_monotonic_guard"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        evidence: list[str] = []
        stale_guard = bool(
            re.search(
                r"(?:event\.)?version\s*<=\s*(?:self\.)?(?:state\.)?version",
                lower,
            )
            or re.search(
                r"(?:event\.)?version\s*<\s*(?:self\.)?(?:state\.)?version",
                lower,
            )
            or "stale" in lower
            or "out_of_order" in lower
            or "updated_at" in lower
            or "sequence" in lower
        )
        blind_apply = bool(
            re.search(
                r"def\s+apply[\s\S]{0,180}self\.state\.(?:status|version)\s*="
                r"\s*event\.(?:status|version)",
                lower,
            )
            and not stale_guard
        )
        passed = stale_guard and not blind_apply
        if stale_guard:
            evidence.append("Stale or out-of-order events are ignored before mutation.")
        if blind_apply:
            evidence.append("Events overwrite state without version ordering.")
            passed = False
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.94 if passed else 0.9,
            message=(
                "State updates ignore stale event versions."
                if passed
                else "Events can overwrite newer state without version checks."
            ),
            evidence=evidence,
        )


class PaginationUsesStableTiebreaker(BaseValidator):
    name = "pagination_uses_stable_tiebreaker"

    def validate(self, context: ValidatorContext) -> ValidatorResult:
        _, text = read_expected_source(context)
        lower = text.lower()
        evidence: list[str] = []
        composite = bool(
            re.search(r"created_at.{0,40}(?:,|\band\b).{0,40}\bid\b", lower, flags=re.DOTALL)
            or re.search(r"\(created_at,\s*id\)", lower)
            or re.search(r"cursor.{0,60}id", lower, flags=re.DOTALL)
        )
        created_only = bool(
            re.search(r"cursor.{0,80}created_at", lower, flags=re.DOTALL) and not composite
        )
        passed = composite and not created_only
        if composite:
            evidence.append("Pagination cursor uses created_at with a stable id tiebreaker.")
        if created_only:
            evidence.append("Pagination cursor relies on created_at without a tiebreaker.")
            passed = False
        return ValidatorResult(
            name=self.name,
            passed=passed,
            confidence=0.95 if passed else 0.9,
            message=(
                "Pagination cursor includes a stable unique tiebreaker."
                if passed
                else "Pagination cursor omits a stable tiebreaker for duplicate timestamps."
            ),
            evidence=evidence,
        )
