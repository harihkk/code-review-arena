# Code Review Arena

Execution-backed benchmark for AI code-review agents.

## Overview

Code Review Arena evaluates whether review agents can detect seeded pull-request bugs
and produce patches that pass deterministic validation. It reports detection and
validation separately so a plausible finding is not confused with a working fix.

The local dashboard presents leaderboard results, benchmark cases, methodology, run
traces, and generated Audit Pack v1 reports.

## Why detection is not validation

`detection_f_beta` records whether the reviewer found and localized the seeded defect.
`validated_f_beta` records whether the finding also produced a patch that applied,
passed required tests, and satisfied required structural validators.

A reviewer can score well on detection and still produce no validated fixes.

## Benchmark packs

| Pack | Cases | Purpose | Primary validation |
|---|---:|---|---|
| `benchmark_sets/v1` | 10 | Baseline harness cases | scoring and validation |
| `benchmark_sets/audit_v1` | 10 | Patch-required audit cases | patch, tests, and validators |

## Audit Pack v1

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
| `detection_f_beta` | Found and localized the seeded bug |
| `validated_f_beta` | Found a bug and produced a deterministically validated fix |
| `patch_apply_rate` | Fraction of required patches that applied cleanly |
| `test_pass_rate` | Fraction of required regression-test executions that passed |
| `structural_pass_rate` | Fraction of required structural validator checks that passed |
| `false_positives_per_case` | Unsupported findings per evaluated case |

`validated_f_beta` is the primary metric for full-mode audit runs.

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

## Run a benchmark

```bash
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena run benchmark_sets/audit_v1 --reviewer mock:keyword_gamer --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0
```

`--allow-local-execution` opts into fixture-owned test commands in copied run
workspaces. Use it only with fixtures you trust.

## Generate report

```bash
arena audit-report runs/ --output docs/reports/audit-v1-results.md
```

This command also writes the JSON snapshot consumed by `/reports/audit-v1`.

## Dashboard

```bash
arena serve
cd dashboard
npm install
npm run dev
```

Open `http://localhost:3000`. The primary pages are `/leaderboard`, `/cases`,
`/reports/audit-v1`, `/methodology`, and `/docs`.

## Limitations

- `audit_v1` is curated and small.
- Structural validators are hand-authored and may reject alternate valid repairs.
- Passing tests supplies execution evidence, not proof of complete correctness.
- Valid fixes can fail when a validator is intentionally narrow.
- Code Review Arena is a local audit harness, not a large-scale public adoption benchmark.

## Development

```bash
make test
make lint
make typecheck
cd dashboard && npm run build
```

## License

MIT. See [LICENSE](LICENSE).
