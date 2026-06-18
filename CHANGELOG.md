# Changelog

All notable changes to this project are recorded here. The format follows the
Keep a Changelog conventions, and the project has not cut a tagged release yet.

## Unreleased

### Added

- Audit Pack v2 (`benchmark_sets/audit_v2`): a second batch of patch-backed cases
  targeting high-impact logic defects (per-unit rounding that loses money, a
  fixed-window rate limiter off-by-one, a boolean-precedence authorization
  bypass). Every case is authored leak-free and fully certified (baseline fails,
  reference fix passes, 100% mutant-kill rate), verified in CI.
- v2 metric model: `validated_case_rate` (unit-coherent primary metric that
  replaces the deprecated `validated_f_beta`) plus three evidence dimensions,
  review accuracy (`bug_completeness_rate`), repair success
  (`complete_repair_rate`), and trustworthiness (`supported_claim_rate`).
  Findings carry a per-finding `evidence_status` and cases a `case_status`.
- Per-case Repair Confidence (`basic` / `strong` / `unvalidated`) derived from
  how deeply a repair was validated (tests alone vs tests plus structural
  validators).
- Mutation testing (`arena mutation-test`): generate single-edit mutants of the
  corrected solution (`after/` + `reference.patch`) and measure the test
  kill rate, evidence that a case's tests catch wrong repairs.
- Pack certification ladder (`arena certify-pack`): cases are graded
  draft / development / certified / verified. Certifying requires the buggy
  baseline to fail, the reference solution to pass, and a mutation kill rate at
  or above the threshold; the top rung adds an opt-in determinism gate
  (`--determinism-runs`) that re-runs the verdicts to reject flaky cases.
- Content-addressed evidence bundles sealed per run, with `arena verify-run` to
  confirm a run's outputs were not altered after the fact.
- Test and oracle tampering detection: a before/after content manifest catches
  candidate code that rewrites hidden tests mid-run, and tampered cases are
  excluded from aggregate metrics, not just flagged.
- Run validity and coverage: a `run_status` of
  complete / partial / invalid / failed / legacy. A run that needed test
  execution but had no available backend is `invalid`; partial and legacy runs
  stay off the leaderboard.
- Per-case and per-run execution backend (`docker` / `trusted-local` / `none`),
  derived weakest-link first; trusted-local runs are unverified and excluded
  from the default leaderboard unless `--include-unverified` is passed.
- Pack-level `default_docker_image` (inherited by cases that do not set their
  own), plus `Dockerfile.bench` and `scripts/build_bench_image.sh` shipping the
  `arena-bench` sandbox image the packs can run their tests in.
- Local-first HTTP reviewer (OpenAI-compatible) for Ollama, vLLM, LM Studio, and
  llama.cpp.
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

### Security

- Packs are rejected at load time if they contain symlinks or special files
  (sockets, devices, FIFOs): an untrusted pack must hold only regular files and
  directories so copying it into a workspace cannot escape its own tree.
- The Docker backend never pulls a missing image (the image name comes from the
  untrusted pack); the image must already be present locally, and `--pull never`
  backs that up.
- Hardened Docker execution: no network, all capabilities dropped,
  no-new-privileges, read-only root with a `noexec` tmpfs, a non-root user, and
  pids / memory / cpu limits, with the resolved image digest recorded. An
  image-declaring case never silently falls back to local execution.
- Local fixture commands run with an allowlisted environment, an isolated empty
  HOME and TMPDIR, POSIX resource limits, a process-tree kill on timeout,
  capped output, and pytest plugin autoload disabled.

### Changed

- Container test commands route through `python -m pytest` so a case whose tests
  import a top-level workspace module collects correctly (the bare `pytest`
  script does not put the workspace root on `sys.path`).
- `max_wall_seconds` is a hard budget: each case's execution timeout is clamped
  to the remaining run deadline rather than only checked between cases.
- A single case-level `proposed_patch` is applied as the repair instead of an
  arbitrary finding's patch; competing finding patches are reported as ambiguous.
- Storage migrated to schema v2: run validity and coverage are persisted, pre-v2
  rows are marked legacy, and the API leaderboard is gated to eligible runs.
- The dashboard leads with `validated_case_rate` and the evidence dimensions
  across the home, leaderboard, audit report, runs, and verify pages, and marks
  `validated_f_beta` deprecated.
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
