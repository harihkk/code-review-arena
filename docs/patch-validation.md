# Patch Validation

Detection is not validation. Comment scoring alone can reward a plausible explanation whose proposed repair does not
compile, does not apply, or does not address the seeded failure. Patch mode makes repair
behavior observable.

## Flow

1. A reviewer emits a `suggested_patch` unified diff on a matched finding.
2. The runner copies the case's snapshot `after/` tree into
   `runs/<run-id>/workspaces/<case-id>/`.
3. The shared Git-authoritative pipeline applies the patch atomically inside an isolated Git
   repository (preflight `git apply --check --index`, then apply; no `--reject`). What
   actually changed is read from the Git tree, not the patch text, and the changed paths and
   modes are validated and protected-path checked there (protected matching is portable and
   case-insensitive). Baseline and final workspace bytes are proven byte-for-byte equal to the
   Git index blobs with filters disabled (`git status` is defense in depth, not the
   byte-equivalence proof), Git subprocess output is bounded while it is read, and Git metadata
   is removed and its removal verified before the workspace is returned. A rejected, malformed,
   or policy-violating patch is recorded as a failed application with a stable reason code plus
   a separate bounded diagnostic, and the candidate workspace never contains `.git` or the
   patch input. See [trusted-evaluation-architecture.md](trusted-evaluation-architecture.md)
   "Phase 1D".
4. Fixture-owned tests are copied into the same workspace only when required for execution.
5. Enabled structural validators inspect the patched files and record evidence.
6. The outcome contributes to `validated_case_rate` only when the case satisfies every
   required deterministic condition.

Benchmark fixtures are never changed. Raw patches, touched files, application errors, test
output tails and validator evidence are saved in JSON, Markdown, HTML and SQLite records.

## Execution Safety

Local test execution is disabled by default and requires `--allow-local-execution`.
When a case declares a Docker image and Docker is available, tests may execute in that
container instead. Commands are passed as argument lists without shell execution and run
only with the isolated workspace as their working directory.

## Limitations

Structural validation proves selected repair properties, not complete program correctness.
Validators therefore accept multiple credible code shapes and are supplemented by tests
where a fixture can express the regression reliably.
