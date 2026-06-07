# Code Review Arena

Execution-backed benchmark for AI code-review agents.

[![CI](https://github.com/harihkk/code-review-arena/actions/workflows/ci.yml/badge.svg)](https://github.com/harihkk/code-review-arena/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

## About

Code Review Arena measures whether an AI review agent can find a seeded bug in a pull
request and actually fix it. It applies each suggested patch in an isolated workspace,
runs the required tests and validators, and scores detection separately from validation,
so a sharp-looking comment is never mistaken for a working repair. Everything runs
locally and the harness is model-agnostic.

## How it works

Each case is a seeded pull request with a known bug, the files a fix should touch, and
the checks a fix must pass. The reviewer sees the diff and the relevant files, never the
ground truth. It returns its findings and an optional patch, and the harness takes it from
there:

```
diff + files  ->  reviewer  ->  patch  ->  apply in workspace  ->  tests  ->  validators  ->  score
```

Every run produces two numbers:

| Metric | What it measures |
|---|---|
| `detection_f_beta` | The reviewer found and localized the seeded bug |
| `validated_f_beta` | Its patch applied, passed the required tests, and satisfied the validators |

The gap between them is the whole point. On `audit_v1` the `mock:keyword_gamer` control
detects all ten bugs (`detection_f_beta=1.000`) yet validates none of its patches
(`validated_f_beta=0.000`), while `reference-patch` validates all ten. `arena audit-report`
and the dashboard show that gap per reviewer.

## Quickstart

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

arena validate benchmark_sets/audit_v1
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0
```

`--allow-local-execution` opts into the fixture-owned test commands that run in copied
workspaces. Use it only with fixtures you trust.

## Benchmark your own model

The built-in reviewers are the deterministic controls and `reference-patch`. To score a
real model, wrap it in any local command that reads the case JSON and prints review JSON,
then point `custom-command` at it. Ground truth is never in that JSON, so a reviewer
cannot pass on metadata alone.

```bash
arena run benchmark_sets/audit_v1 \
  --reviewer custom-command \
  --command "python scripts/fake_reviewer.py --case {case_json}" \
  --mode full \
  --allow-local-execution
```

`scripts/fake_reviewer.py` is a working example to copy. The placeholders `{case_json}`,
`{diff_file}`, `{case_id}`, and `{workspace}` are expanded per case.

## Reports and dashboard

```bash
arena audit-report runs/ --output docs/reports/audit-v1-results.md   # build the report from saved runs

arena serve            # local API
cd dashboard
npm install
npm run dev            # dashboard at http://localhost:3000
```

Main dashboard routes are `/leaderboard`, `/reports/audit-v1`, `/cases`, `/methodology`,
and `/docs`. For a full walk-through from a fresh clone, see [docs/DEMO.md](docs/DEMO.md).

## Reference

Benchmark packs:

| Pack | Cases | Purpose | Validation |
|---|---:|---|---|
| `benchmark_sets/v1` | 10 | Baseline harness cases | review scoring + validation |
| `benchmark_sets/audit_v1` | 10 | Patch-required audit cases | patch apply + tests + validators |

Metrics:

| Metric | Meaning |
|---|---|
| `validated_f_beta` | Primary full-mode score for deterministically validated fixes |
| `detection_f_beta` | Found and localized seeded bugs |
| `patch_apply_rate` | Required patches that applied cleanly |
| `test_pass_rate` | Required regression-test runs that passed |
| `structural_pass_rate` | Required structural validator checks that passed |
| `false_positives_per_case` | Unsupported findings per evaluated case |

Control reviewers (deterministic harness checks, not external model results):

| Reviewer | Role |
|---|---|
| `reference-patch` | Loads committed known-good `reference.patch` artifacts |
| `mock:perfect_patch` | Harness success control |
| `mock:keyword_gamer` | Detection-only adversarial control |
| `mock:bad_patch` | Detects bugs but supplies failing fixes |
| `mock:detects_no_patch` | Detects bugs without a patch |
| `mock:malformed_patch` | Supplies invalid patch output |
| `custom-command` | Runs your local reviewer command over structured input and output |

Audit Pack v1 cases:

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

## Development

```bash
make test
make lint
make typecheck
cd dashboard && npm run build
```

See [docs/](docs/README.md) for architecture, metrics, the reviewer interface, case
authoring, and the audit report.

## Limitations

- `audit_v1` is curated and small.
- Structural validators are hand-authored and may reject alternate valid repairs.
- Passing tests is execution evidence, not proof of complete correctness.
- A valid fix can still fail when a validator is intentionally narrow.
- This is a local audit harness, not a large-scale public ranking.

## License

MIT. See [LICENSE](LICENSE).
