# Reviewer Interface

Reviewers implement `BaseReviewer.review(context)` and return a `ReviewerResponse`.
`CaseContext` provides the pull-request diff, buggy relevant files, optional failed-test
output and optional analysis output. It deliberately omits the `ground_truth` object.

Provider implementations should render `prompt_templates.SYSTEM_PROMPT`, request JSON,
record latency and usage when available, and route output through `parse_review_response`.
Patch-capable findings may provide `suggested_patch` as a unified diff,
`replacement_code`, and `patch_confidence`. Providers must return valid JSON without
Markdown fences; a natural-language `suggested_fix` alone remains valid for review mode
but cannot satisfy required patch validation.

The mock modes (`perfect`, `partial`, `false-positive`, `invalid_json`,
`perfect_patch`, `bad_patch`, `detects_no_patch`, `false_positive_patch`,
`malformed_patch`, and `keyword_gamer`) are deterministic testing baselines, not model
comparisons. `keyword_gamer` emits plausible, keyword-rich reviews with superficial
patches that fail validation; see [metrics.md](metrics.md#adversarial-baseline-keyword_gamer).

`reference-patch` loads each case’s static `reference.patch` file from the benchmark pack.
Use it to validate known-good case artifacts and the full deterministic pipeline, not to
compare model performance. It does not synthesize patch bytes at runtime; missing
`reference.patch` files produce a structured no-patch finding and fail validation cleanly.
See [audit-pack-v1.md](audit-pack-v1.md#reference-patches).
