# Changelog

All notable changes to this project are recorded here. The format follows the
Keep a Changelog conventions, and the project has not cut a tagged release yet.

## Unreleased

### Added

- Multi-bug ground truth (`ground_truth.bugs` with one-to-one finding matching,
  `acceptable_findings` scored neutral); `primary_bug` remains as an alias.
- Patch integrity guards: patches touching tests, pytest config files, or per-case
  `protected_paths` are rejected, as are absolute or `..` diff paths.
- Blind reviewer payload by default; `--reveal-metadata` restores descriptive
  fields for debugging only.
- Bounded reviewer context with a `context_truncated` signal (env-tunable limits).
- Allowlisted environment and POSIX resource limits for locally executed fixture
  commands; `ARENA_PASSTHROUGH_ENV` forwards named variables explicitly.
- `arena pack-hash` content checksums recorded per run and verified against a
  pinned `pack.sha256` (now shipped for both packs); leaderboard shows
  pack@checksum with a tamper flag.
- API server: run creation enqueues bounded background jobs (202 + job polling),
  optional `ARENA_API_TOKEN`, and a server-side `ARENA_SERVER_ALLOW_LOCAL_EXECUTION`
  opt-in before HTTP callers may trigger local execution.
- `--max-wall-seconds` / `--max-cost` run budgets with clean partial results.
- `run_manifest.json` per run (harness version, git SHA, pack checksum, sanitized
  reviewer config, budgets, timings) plus a determinism regression test.
- `arena schema` (versioned reviewer output contract), `arena verify-reviewer`
  (one-case contract check with actionable errors), and opt-in `--enable-repair`
  deterministic JSON salvage.
- `arena lint-cases` contamination scan for ground-truth vocabulary leaking into
  diffs, comments, or test names.

### Changed

- Scoring: per-case `scoring.weights` are now actually applied; detection is
  judged at file granularity with line precision reported separately
  (`localization_rate`); the false-positive penalty is capped
  (`false_positive_penalty_cap`); execution evidence overrides keyword
  fix-quality in patch/full mode; `correct_line` derives from an explicit
  line-match quality instead of magic score values.
- Structural validators match comment-stripped source so comment-only "fixes"
  fail; the JWT validator inspects function bodies via AST.
- Control reviewers renamed `mock:*` → `control:*` (module
  `arena.reviewers.controls`); `mock:*` stays as a deprecated alias for one
  release. `semantic_matcher` renamed to `concept_matcher` (it is lexical).
- SQLite opens with WAL + busy timeout and versioned idempotent migrations;
  arena refuses databases newer than it understands.
- Test commands parse strictly (string, argv list, or list of argv commands; no
  shell operators) and are checked at `arena validate` time.
- Default paths resolve against `ARENA_PROJECT_ROOT` or a discovered project
  root so commands behave the same from any directory.

- Reworked the audit report page into compact case-study cards and laid the
  detection versus validation gap out as a grid instead of stacked full-width rows.
- Compacted the leaderboard so it fits the page without horizontal scrolling and
  keeps each reviewer on a single line.
- Collapsed the cases table into one requirements column, with the full validator
  names tucked behind an expandable summary.
- Widened the content area and let the documentation index fill the page at three
  cards per row.
- Reviewer names now read as plain labels such as "Control: Perfect Repair" across
  the dashboard, and the control-baseline note appears wherever controls are shown.

### Removed

- Dropped the duplicate control tag that sat next to reviewer names, since the name
  already says it is a control.
- Removed reviewer helper functions that were no longer referenced.
