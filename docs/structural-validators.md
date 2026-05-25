# Structural Validators

Structural validators provide deterministic evidence that a patch contains the safety
property implied by a seeded defect. They complement regression tests rather than replacing
them.

## Registry

Validators implement `BaseValidator.validate(ValidatorContext) -> ValidatorResult` and
are registered by name in `arena/validators/registry.py`. A case enables validators in
`case.yaml`:

```yaml
validation:
  patch_required: true
  structural_validators:
    - fastapi_requires_admin_authorization
```

The context includes the isolated patched workspace, touched files, matched finding and
trusted case metadata. Results include pass/fail, confidence, a message and concrete
evidence.

## Design Principle

Validators must accept multiple valid repair styles. For example, the FastAPI validator
accepts an administrator dependency, a permission helper, or an explicit role denial
path. A validator should establish the required safety property, not require one mock
patch's exact spelling.

## Adding A Validator

1. Add a `BaseValidator` implementation in the most relevant module under `arena/validators`.
2. Inspect only files in `context.workspace_path`.
3. Use AST parsing where helpful and cautious textual fallbacks for framework syntax.
4. Register its stable string name.
5. Add positive and negative unit tests before assigning it to a case.

## Included Validators

- `fastapi_requires_admin_authorization`
- `kafka_idempotency_guard`
- `redis_cache_key_has_tenant_scope`
- `sql_has_tenant_or_owner_filter`
- `rag_citation_ids_validated`
- `rag_retrieved_context_is_untrusted`
- `jwt_audience_issuer_validated`
- `event_version_monotonic_guard`
- `pagination_uses_stable_tiebreaker`
- `react_uses_functional_state_update`
- `graphql_uses_batching_or_dataloader`
