# Reviewer Interface

A reviewer implements `BaseReviewer.review(context)` and returns a `ReviewerResponse`.
`CaseContext` provides the pull-request diff, the buggy relevant files, and optional
failed-test or static-analysis output. It omits the `ground_truth` object, so a reviewer
cannot read the seeded location or the gold patch.

A finding may carry `suggested_patch` (a unified diff), `replacement_code`, and
`patch_confidence`. A natural-language `suggested_fix` alone is valid for review mode but
cannot satisfy patch validation in full mode.

## Built-in reviewers

- `control:<mode>`: deterministic controls for testing the harness, not model comparisons.
  Modes: `perfect`, `partial`, `false_positive`, `invalid_json`, `perfect_patch`,
  `bad_patch`, `detects_no_patch`, `false_positive_patch`, `malformed_patch`,
  `keyword_gamer`. `keyword_gamer` emits keyword-rich reviews with superficial patches
  that fail validation; see [metrics.md](metrics.md#adversarial-baseline-keyword_gamer).
- `reference-patch`: loads each case's static `reference.patch`. Use it to validate the
  fixtures and the full pipeline, not to compare models. A missing `reference.patch`
  produces a structured no-patch finding that fails validation cleanly. See
  [reference-patches.md](reference-patches.md).
- `custom-command`: benchmarks any external process, which keeps the harness
  model-agnostic.

## Custom command

`custom-command` writes the reviewer-visible case to a JSON file (via
`serialize_reviewer_case`, which excludes ground truth) and runs your command. These
placeholders are expanded per case: `{case_json}`, `{diff_file}`, `{case_id}`,
`{workspace}`. The command prints review JSON to stdout with no Markdown fences; the
output is parsed by `parse_review_response`. See
[custom-command-reviewer.md](custom-command-reviewer.md) for a worked example.
