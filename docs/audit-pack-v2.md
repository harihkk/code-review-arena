# Audit Pack v2

Audit Pack v2 is a second batch of patch-backed cases. Where v1 leans on
domain-shaped failures (auth, distributed systems, RAG), v2 targets small but
high-impact logic defects: the kind that pass a casual read yet change behavior
in production. Every case is authored leak-free (no ground-truth vocabulary in
the diff, comments, or test names) and fully certified (the buggy baseline
fails, the reference fix passes, and the tests kill every viable mutant).

## Cases

| ID | Focus |
|---|---|
| `money_discount_rounding_001` | Per-unit reduction floors and loses money on multi-unit orders |
| `ratelimit_window_boundary_001` | Fixed-window limiter admits one request past the cap |
| `permission_precedence_001` | Boolean precedence drops grouping and bypasses a guard |
| `overdraft_min_balance_001` | Lowest-balance tracker compares the wrong direction |
| `progress_zero_division_001` | Completion percentage drops its empty-workload guard |
| `page_count_ceil_001` | Page count floors instead of ceilings and drops the last page |
| `truthiness_default_001` | Fallback uses truthiness and discards an explicit zero |
| `preview_truncation_001` | Text preview truncates one character short of the limit |
| `retry_backoff_cap_001` | Backoff delay drops its clamp and grows without bound |
| `eligibility_and_or_001` | Eligibility check uses `or` where both conditions are required |

## Reference patches

Each case ships a static `reference.patch` beside `case.yaml`: the canonical
known-good unified diff for that case's `after/` tree. The `reference-patch`
reviewer loads it, applies it, and validates against the hidden tests.

```bash
arena run benchmark_sets/audit_v2 --reviewer reference-patch --mode full --allow-local-execution
```

Expect `validated_case_rate=1.000` and `deterministic_pass_rate=100%`.

## Certification

Every case is certified: the `after/` baseline fails the tests, `after/` plus
`reference.patch` passes them, and the tests kill every viable mutant of the
fixed solution (a 100% mutant-kill rate). That mutant-kill gate is the pack's
cheat-resistance evidence: a superficial patch that looks right but changes
behavior is caught by the tests.

```bash
arena certify-pack benchmark_sets/audit_v2 --allow-local-execution --strict certified
arena lint-cases benchmark_sets/audit_v2 --strict
```

## Adversarial baseline

`shallow-patch` is a generic adversarial reviewer that works on any pack: it reads
the reference patch only to localize the bug, then proposes a no-op change that
applies cleanly but repairs nothing. On this pack it scores `detection_f_beta`
near 1.0 with `validated_case_rate` 0.0, the detection-versus-validation gap that
is the whole point of the harness.

```bash
arena run benchmark_sets/audit_v2 --reviewer shallow-patch --mode full --allow-local-execution
```

## Metrics

- `detection_f_beta` measures whether the reviewer localized the seeded bug.
- `validated_case_rate` is the primary full-mode metric and requires the patch to
  apply and the tests to pass.

Detection is not validation.
