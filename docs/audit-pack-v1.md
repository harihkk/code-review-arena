# Audit Pack v1

Audit Pack v1 is a harder benchmark pack focused on patch-backed review failures. The pack
includes 10 cases across security, distributed systems, RAG safety, concurrency,
idempotency, API correctness, and pagination.

## Cases

| ID | Focus |
|---|---|
| `security_fastapi_multitenant_admin_bypass_001` | Tenant-scoped admin authorization |
| `distributed_kafka_duplicate_event_001` | Kafka duplicate delivery |
| `rag_fabricated_citation_001` | RAG citation grounding |
| `async_balance_race_001` | Async lost updates |
| `idempotency_key_tenant_scope_001` | Tenant-scoped idempotency keys |
| `security_sql_join_ownership_leak_001` | SQL join ownership leak |
| `security_jwt_audience_validation_001` | JWT audience and issuer validation |
| `distributed_out_of_order_event_001` | Out-of-order event projection |
| `api_pagination_cursor_skip_001` | Pagination cursor tiebreaker |
| `rag_prompt_injection_policy_override_001` | RAG prompt injection isolation |

## Reference patches

Each audit_v1 case ships a static `reference.patch` beside `case.yaml`. The file is the
canonical known-good unified diff for that case's `after/` tree: it applies cleanly, passes
regression tests, and satisfies structural validators. Contributors can inspect or replay the
fix without reading mock reviewer internals.

`reference-patch` is the reviewer that loads these artifacts. `control:perfect_patch` proves
the harness happy path by synthesizing equivalent fixes internally; `reference-patch` proves
the same outcome using normal, human-readable patch files stored in the benchmark pack.

```bash
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
```

Expect `validated_f_beta=1.000` and `deterministic_pass_rate=100%` when every
`reference.patch` is present.

## Commands

```bash
arena validate benchmark_sets/audit_v1
arena run benchmark_sets/audit_v1 --reviewer control:perfect_patch --mode full --allow-local-execution
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0
arena audit-report runs/ --output docs/reports/audit-v1-results.md
```

## Metrics

- `detection_f_beta` measures whether the reviewer localized the seeded bug.
- `validated_f_beta` is the primary full-mode metric and requires patch apply, tests, and structural validators to pass.

Detection is not validation.
