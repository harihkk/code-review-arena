# CodeReview Arena

Execution-backed benchmark for AI code-review agents.

[![CI](https://github.com/harihkk/code-review-arena/actions/workflows/ci.yml/badge.svg)](https://github.com/harihkk/code-review-arena/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

## Overview

CodeReview Arena evaluates whether review agents can detect seeded pull-request bugs
and produce patches that pass deterministic validation. It reports detection and
validation separately so a plausible finding is not confused with a working fix.

The project includes a local CLI, two benchmark packs, deterministic controls,
custom-command reviewer support, saved run traces, and a dashboard for leaderboard and
report inspection.

## Detection vs validation

| Metric | Signal |
|---|---|
| `detection_f_beta` | Reviewer found and localized the seeded bug |
| `validated_f_beta` | Reviewer produced a patch that applied, passed tests, and satisfied validators |

The split matters because a reviewer can detect the right issue while still producing no
usable repair. On `audit_v1`, the `mock:keyword_gamer` control detects all ten seeded bugs
(`detection_f_beta=1.000`) but validates none of its patches (`validated_f_beta=0.000`),
while `reference-patch` validates all ten (`validated_f_beta=1.000`). `arena audit-report`
and the dashboard surface that gap per reviewer.

## Benchmark packs

| Pack | Cases | Purpose | Validation |
|---|---:|---|---|
| `benchmark_sets/v1` | 10 | Baseline harness cases | review scoring + validation |
| `benchmark_sets/audit_v1` | 10 | Patch-required audit cases | patch apply + tests + validators |

## Audit Pack v1 cases

| Category | Seeded bug |
|---|---|
| Security | FastAPI tenant admin bypass |
| Security | SQL ownership leak |
| Security | JWT audience and issuer validation |
| Distributed systems | Kafka duplicate event |
| Distributed systems | Out-of-order event |
| RAG safety | Fabricated citation |
| RAG safety | Prompt injection policy override |
| Concurrency | Async race |
| Reliability | Idempotency tenant scope |
| API correctness | Pagination cursor bug |

## Metrics

| Metric | Meaning |
|---|---|
| `validated_f_beta` | Primary full-mode score for deterministically validated fixes |
| `detection_f_beta` | Found and localized seeded bugs |
| `patch_apply_rate` | Required patches that applied cleanly |
| `test_pass_rate` | Required regression-test executions that passed |
| `structural_pass_rate` | Required structural validator checks that passed |
| `false_positives_per_case` | Unsupported findings per evaluated case |

## Baselines

| Reviewer | Role |
|---|---|
| `reference-patch` | Loads committed known-good `reference.patch` artifacts |
| `mock:perfect_patch` | Deterministic harness success control |
| `mock:keyword_gamer` | Detection-only adversarial control |
| `mock:bad_patch` | Detects bugs while supplying failing fixes |
| `mock:detects_no_patch` | Detects bugs without patch output |
| `mock:malformed_patch` | Supplies invalid patch output |
| `custom-command` | Invokes a local reviewer command using structured input and output |

Reference and mock rows are deterministic controls, not external model results.

## Quickstart

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
arena validate benchmark_sets/audit_v1
```

## Run benchmarks

```bash
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena run benchmark_sets/audit_v1 --reviewer mock:keyword_gamer --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0
```

`--allow-local-execution` opts into fixture-owned test commands in copied run
workspaces. Use it only with fixtures you trust.

## Custom reviewers

CodeReview Arena is model-agnostic. It ships no vendor adapters and makes no model
performance claims; the built-in reviewers are the deterministic controls and
`reference-patch`. To benchmark a real model, wrap it in any local command that reads
the case JSON on stdin/args and prints structured review JSON, then point
`custom-command` at it. Ground truth is never included in that JSON, so a reviewer
cannot pass on metadata alone.

A working example reviewer ships in `scripts/fake_reviewer.py`:

```bash
arena run benchmark_sets/audit_v1 \
  --reviewer custom-command \
  --command "python scripts/fake_reviewer.py --case {case_json}" \
  --mode full \
  --allow-local-execution
```

Swap that command for your own reviewer process. The template placeholders
`{case_json}`, `{diff_file}`, `{case_id}`, and `{workspace}` are expanded per case.

## Reports and dashboard

Generate an audit report from saved run artifacts:

```bash
arena audit-report runs/ --output docs/reports/audit-v1-results.md
```

Run the API and dashboard locally:

```bash
arena serve
cd dashboard
npm install
npm run dev
```

Primary dashboard routes are `/leaderboard`, `/reports/audit-v1`, `/cases`,
`/methodology`, and `/docs`.

For a full walk-through from a fresh clone, see [docs/DEMO.md](docs/DEMO.md).

## Documentation

See [docs/](docs/README.md) for architecture, metrics, the reviewer interface, case
authoring, and the audit report.

## Development

```bash
make test
make lint
make typecheck
cd dashboard && npm run build
```

## Limitations

- `audit_v1` is curated and small.
- Structural validators are hand-authored and may reject alternate valid repairs.
- Passing tests supplies execution evidence, not proof of complete correctness.
- Valid fixes can fail when a validator is intentionally narrow.
- CodeReview Arena is a local audit harness, not a large-scale public ranking.

## License

MIT. See [LICENSE](LICENSE).
