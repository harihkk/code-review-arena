# Adding New Cases

Create a new directory under a versioned benchmark set containing:

```text
case.yaml
before/
after/
pr.diff
tests/       # optional
```

The `after/` tree must contain the buggy changed file and every ground-truth line range must
be valid in that file. The diff should be a standard unified diff whose `b/` paths match
the paths inside `after/`.

Choose concepts and required phrases that identify the production failure, not superficial
syntax. Choose fix keywords that reward concrete remediation without prescribing one exact
implementation. When `execution.run_tests` is true, the command executes in a temporary
copy of `after/` plus `tests/`.

Declare patch requirements, optional tests, and tolerant structural validators in the
case metadata. Finally update `manifest.yaml`, then run:

```bash
arena validate benchmark_sets/v1
arena run benchmark_sets/v1 --reviewer control:perfect_patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0
pytest
```
