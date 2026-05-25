"""Registry and orchestration for structural validators."""

from __future__ import annotations

from arena.validators.base import BaseValidator, ValidatorContext, ValidatorResult
from arena.validators.javascript_static import (
    GraphQLUsesBatchingOrDataLoader,
    ReactUsesFunctionalStateUpdate,
)
from arena.validators.python_ast import (
    AsyncUpdateAtomicityGuard,
    EventVersionMonotonicGuard,
    FastAPIRequiresAdminAuthorization,
    FastAPITenantAdminAuthorization,
    JWTAudienceIssuerValidated,
    KafkaIdempotencyGuard,
    PaginationUsesStableTiebreaker,
    RedisCacheKeyHasTenantScope,
    TenantScopedIdempotencyKey,
)
from arena.validators.rag_validators import RAGCitationIdsValidated, RAGRetrievedContextIsUntrusted
from arena.validators.sql_static import SQLHasTenantOrOwnerFilter

_VALIDATORS: dict[str, type[BaseValidator]] = {
    "fastapi_requires_admin_authorization": FastAPIRequiresAdminAuthorization,
    "fastapi_tenant_admin_authorization": FastAPITenantAdminAuthorization,
    "kafka_idempotency_guard": KafkaIdempotencyGuard,
    "async_update_atomicity_guard": AsyncUpdateAtomicityGuard,
    "tenant_scoped_idempotency_key": TenantScopedIdempotencyKey,
    "redis_cache_key_has_tenant_scope": RedisCacheKeyHasTenantScope,
    "sql_has_tenant_or_owner_filter": SQLHasTenantOrOwnerFilter,
    "rag_citation_ids_validated": RAGCitationIdsValidated,
    "rag_retrieved_context_is_untrusted": RAGRetrievedContextIsUntrusted,
    "jwt_audience_issuer_validated": JWTAudienceIssuerValidated,
    "event_version_monotonic_guard": EventVersionMonotonicGuard,
    "pagination_uses_stable_tiebreaker": PaginationUsesStableTiebreaker,
    "react_uses_functional_state_update": ReactUsesFunctionalStateUpdate,
    "graphql_uses_batching_or_dataloader": GraphQLUsesBatchingOrDataLoader,
}


def get_validator(name: str) -> BaseValidator:
    try:
        return _VALIDATORS[name]()
    except KeyError as exc:
        raise KeyError(f"Unknown structural validator: {name}") from exc


def run_validators(names: list[str], context: ValidatorContext) -> list[ValidatorResult]:
    results: list[ValidatorResult] = []
    for name in names:
        try:
            results.append(get_validator(name).validate(context))
        except (KeyError, OSError, ValueError) as exc:
            results.append(
                ValidatorResult(
                    name=name,
                    passed=False,
                    confidence=1.0,
                    message="Validator could not evaluate the patched workspace.",
                    error=str(exc),
                )
            )
    return results
