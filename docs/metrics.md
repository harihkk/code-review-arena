# Metrics

Detection is not validation. CodeReview Arena reports two metric tiers because a
reviewer can correctly point at a defect while supplying no usable repair.

## Detection Tier

A detection true positive is a case whose seeded bug was detected and localized to the
expected code. Unmatched reviewer findings are false positives.

| Metric | Definition |
|---|---|
| `detection_precision` | Localized detections / (localized detections + unmatched findings) |
| `detection_recall` | Localized detections / total seeded cases |
| `detection_f1` | Balanced harmonic mean of detection precision and recall |
| `detection_f_beta` | Weighted harmonic mean of detection precision and recall |

## Validation Tier

A validated true positive is a case where `deterministic_pass` is true. This requires
detection and localization, plus every configured patch application, required test,
required structural validator, and false-positive threshold condition.

| Metric | Definition |
|---|---|
| `validated_precision` | Deterministic passes / (deterministic passes + unmatched findings) |
| `validated_recall` | Deterministic passes / total seeded cases |
| `validated_f1` | Balanced harmonic mean of validated precision and recall |
| `validated_f_beta` | Weighted harmonic mean; the primary full/patch-mode metric |

`beta=0.5` emphasizes precision, `beta=1.0` is balanced, and `beta=2.0` emphasizes
recall. The legacy CLI metric name `f_beta` aliases `detection_f_beta`, so older scripts
continue to run without confusing it with validated repair success.

## Execution Outcomes

| Metric | Definition |
|---|---|
| `deterministic_pass_rate` | Cases passing all deterministic requirements / cases evaluated |
| `patch_apply_rate` | Cleanly applied patches / patches provided |
| `test_pass_rate` | Passed post-patch test executions / tests run |
| `structural_pass_rate` | Passed validators / validators run |
| `false_positives_per_case` | Total unmatched findings / cases evaluated |
| `cost_per_validated_fix` | Estimated total model cost / deterministic passes |
| `latency_per_case_ms` | Total reviewer latency / cases evaluated |

The original 100-point score is retained as `review_quality_score`; it is useful
secondary evidence for localization and comment quality, not the primary outcome metric.

```bash
arena leaderboard runs/ --metric validated_f_beta --beta 1.0
arena leaderboard runs/ --metric detection_f_beta --beta 0.5
arena leaderboard runs/ --metric patch_apply_rate
```

## Adversarial baseline: keyword_gamer

`mock:keyword_gamer` is a deterministic adversarial reviewer for audit packs. It localizes
every seeded bug with plausible, keyword-rich findings (tenant scope, idempotency,
citation validation, audience/issuer, cursor tiebreakers, and similar validator language)
and always supplies a `suggested_patch`. The patch sounds credible but is superficial: it
may apply cleanly yet still fails regression tests and structural validators.

On `audit_v1`, expect `detection_f_beta` near 1.0, `validated_f_beta` at 0.0, and
`deterministic_pass_rate` at 0%. Failure reasons should include
`structural_validation_failed`, `tests_failed`, or `patch_apply_failed`. This baseline
shows why `validated_f_beta` is the primary full-mode metric: high detection scores alone
do not prove a repair.

```bash
arena run benchmark_sets/audit_v1 --reviewer mock:keyword_gamer --mode full --allow-local-execution
```
