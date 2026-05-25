# Patch Validation

Detection is not validation. Comment scoring alone can reward a plausible explanation whose proposed repair does not
compile, does not apply, or does not address the seeded failure. Patch mode makes repair
behavior observable.

## Flow

1. A reviewer emits a `suggested_patch` unified diff on a matched finding.
2. The runner copies the case's buggy `after/` tree into
   `runs/<run-id>/workspaces/<case-id>/`.
3. `git apply --whitespace=nowarn` applies the patch in that copy. A rejected or malformed
   patch is recorded as a failed application.
4. Fixture-owned tests are copied into the same workspace only when required for execution.
5. Enabled structural validators inspect the patched files and record evidence.
6. The outcome contributes to `validated_f_beta` only when the case satisfies every
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
