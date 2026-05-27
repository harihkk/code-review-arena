# Code Review Arena Report

Benchmark Set: v1
Reviewer: mock:perfect
Run ID: 2026-05-25_14-49-53

## Summary

| Metric | Value |
|---|---:|
| Total Score | 100.0 |
| Bugs Found | 10/10 |
| Correct File | 10/10 |
| Correct Line | 10/10 |
| False Positives | 0 |
| Estimated Cost | $0.0000 |
| Total Latency | 0.00s |

## Case Results

### fastapi_auth_bypass_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Missing authorization check on admin endpoint.

Reviewer Finding:  
Missing authorization check on admin endpoint. This concerns authorization role-based access control privilege escalation admin role authorization.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### spring_boot_null_handling_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Missing records now cause an Optional runtime exception instead of a 404.

Reviewer Finding:  
Missing records now cause an Optional runtime exception instead of a 404. This concerns missing record Optional not found findById empty exception.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### graphql_n_plus_one_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Customer lookups inside the order map introduce N+1 database queries.

Reviewer Finding:  
Customer lookups inside the order map introduce N+1 database queries. This concerns N+1 batching database query customer loop query.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### react_stale_state_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Async updates close over stale messages state and can drop notifications.

Reviewer Finding:  
Async updates close over stale messages state and can drop notifications. This concerns stale state functional update asynchronous update messages stale state.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### kafka_idempotency_bug_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Payment updates are no longer idempotent for duplicate Kafka events.

Reviewer Finding:  
Payment updates are no longer idempotent for duplicate Kafka events. This concerns idempotency duplicate event at-least-once delivery event_id duplicate credit.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### redis_cache_key_collision_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Under-specified Redis keys leak cached search data across tenants and queries.

Reviewer Finding:  
Under-specified Redis keys leak cached search data across tenants and queries. This concerns cache key collision tenant isolation data leakage tenant_id query cache.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### sql_permission_leak_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Document access omits organization ownership filtering.

Reviewer Finding:  
Document access omits organization ownership filtering. This concerns authorization tenant isolation data exposure organization_id document ownership.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### rag_fake_citation_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Generated citation IDs are not validated against retrieved context.

Reviewer Finding:  
Generated citation IDs are not validated against retrieved context. This concerns citation validation retrieved context fabricated citation citation_ids retrieved_chunks validate.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### async_race_condition_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Concurrent balance mutations are non-atomic and can lose writes.

Reviewer Finding:  
Concurrent balance mutations are non-atomic and can lose writes. This concerns race condition atomic update lost write concurrent balance lock.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

### api_contract_regression_001

Score: 100.0/100  
Bug Found: yes  
Correct File: yes  
Correct Line: full  
False Positives: 0

Ground Truth:  
Renamed response fields break existing clients expecting snake_case keys.

Reviewer Finding:  
Renamed response fields break existing clients expecting snake_case keys. This concerns backward compatibility response schema API contract snake_case camelCase client.

Scoring:
- Concept Match: 35.0/35
- File Match: 20.0/20
- Line Overlap: 15.0/15
- Severity Match: 10.0/10
- Fix Quality: 15.0/15
- False Positive Score: 5.0/5

## False Positive Summary

None.

## Missed Bug Summary

None.

## Cost And Latency Summary

| Metric | Value |
|---|---:|
| Estimated Cost | $0.0000 |
| Total Latency | 0.00s |
| Cost per Detected Bug | $0.0000 |
