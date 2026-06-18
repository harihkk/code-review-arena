# Contributing

Thanks for helping improve CodeReview Arena. This guide covers the local setup,
the checks that must pass, and how to add a benchmark case correctly.

## Setup

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
make install
```

## The checks

Run the full local gate before opening a pull request. It mirrors CI's backend
job (lint, type check, tests, pack validation, contamination scan):

```bash
make check
```

Individual targets are also available: `make lint`, `make format`, `make
typecheck`, `make test`, `make validate`, `make lint-cases`, `make certify`.
The dashboard has its own build gate:

```bash
cd dashboard && npm ci && npm run build
```

## Adding a benchmark case

A case is a seeded pull request: the reviewer sees a diff and the changed files,
and the harness checks whether a proposed repair actually fixes the bug. Layout:

```
benchmark_sets/<pack>/<case_id>/
  before/         # the correct pre-PR state
  after/          # the buggy PR state the reviewer sees
  tests/          # hidden tests: pass on the fix, fail on the bug
  pr.diff         # before -> after (what the reviewer reviews)
  reference.patch # after -> fixed (the canonical repair, git-apply format)
  case.yaml       # metadata and ground truth
```

Conventions that keep a case trustworthy:

- **Direction.** `before/` is correct, `after/` is buggy. `pr.diff` is the
  before-to-after diff (it introduces the bug). `reference.patch` is the
  after-to-fixed diff and must apply to `after/` with `git apply` (include a
  trailing context line so it applies cleanly).
- **No answer leaks.** The ground-truth vocabulary (`must_mention`, `concepts`,
  `acceptable_fix_keywords`) must not appear in the `pr.diff` added lines, in
  `after/` comments, or in test names. `arena lint-cases <pack> --strict`
  enforces this. Use generic identifiers in code and conceptual terms in the
  ground truth.
- **Make it certifiable.** The buggy `after/` must fail the tests, `after/` plus
  `reference.patch` must pass them, and the tests must kill mutants of the fixed
  code. Put the bug in arithmetic, comparison, or boolean logic so mutation
  testing exercises it (the operators cover `+ - * /`, comparisons, `and`/`or`,
  and boolean constants).

Then register and verify the case:

```bash
# add the case id to benchmark_sets/<pack>/manifest.yaml, then:
arena validate benchmark_sets/<pack>
arena lint-cases benchmark_sets/<pack> --strict
arena certify-pack benchmark_sets/<pack> --allow-local-execution --strict certified
arena run benchmark_sets/<pack> --reviewer reference-patch --mode full --allow-local-execution
arena pack-hash benchmark_sets/<pack> --write    # repin the content checksum
```

For accurate detection scoring, add a localization hint for the case in
`arena/reviewers/reference_patch.py` (this is reviewer-side knowledge, not part
of the case, so it does not count as contamination).

## Pull requests

- Keep commits focused; split unrelated changes.
- Write commit messages and code comments in plain ASCII.
- Make sure `make check` and the dashboard build are green.
