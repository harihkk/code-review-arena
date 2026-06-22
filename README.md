# Code Review Arena

A local benchmark for automated code-review systems.

[![CI](https://github.com/harihkk/code-review-arena/actions/workflows/ci.yml/badge.svg)](https://github.com/harihkk/code-review-arena/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

Code Review Arena checks two things:

- Did the reviewer find the seeded defect?
- Did its proposed patch actually work?

The harness applies patches in disposable workspaces, runs the required tests and validators, and reports detection separately from validated repair.

## Quickstart

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

arena validate benchmark_sets/audit_v1
arena run benchmark_sets/audit_v1 \
  --reviewer reference-patch \
  --mode full \
  --allow-local-execution

arena leaderboard runs/ \
  --metric validated_case_rate \
  --include-unverified
```

`--allow-local-execution` runs fixture-owned commands on the host. Use it only with packs you trust. These runs are marked as trusted-local and are excluded from the default leaderboard.

## How it works

Each case contains a seeded defect, the files visible to the reviewer, and the checks a repair must pass.

```text
diff + files -> reviewer -> proposed patch -> tests and validators -> score
```

Reviewer input is blind by default. It does not include ground truth, severity, category, or failing test output unless a development flag explicitly enables that data.

Exact JSON is the default reviewer contract. Deterministic salvage is available for development, but salvaged runs are excluded from the default leaderboard.

## Main metrics

| Metric | Meaning |
|---|---|
| `detection_f_beta` | How well the reviewer found the seeded defects |
| `validated_case_rate` | How often the proposed repair applied and passed the required checks |
| `patch_apply_rate` | How often required patches applied cleanly |
| `test_pass_rate` | How often required tests passed |
| `false_positives_per_case` | Unsupported findings per case |

The gap between detection and validated repair is intentional. A reviewer can describe the right problem and still submit a broken patch.

## Included packs

| Pack | Cases | Purpose |
|---|---:|---|
| `benchmark_sets/v1` | 10 | Baseline scoring cases |
| `benchmark_sets/audit_v1` | 10 | Patch-required review failures |
| `benchmark_sets/audit_v2` | 10 | Certified logic-defect cases |

## Run your own reviewer

A custom reviewer is any local command that reads the case payload and prints review JSON.

```bash
arena schema

arena verify-reviewer benchmark_sets/audit_v1 \
  --command "python scripts/fake_reviewer.py --case {case_json}"

arena run benchmark_sets/audit_v1 \
  --reviewer custom-command \
  --command "python scripts/fake_reviewer.py --case {case_json}" \
  --mode full \
  --allow-local-execution
```

`scripts/fake_reviewer.py` is a small working example. Supported placeholders include `{case_json}`, `{diff_file}`, `{case_id}`, and `{workspace}`.

## Docker execution

Docker is the standard execution path for comparable full-mode runs.

```bash
bash scripts/build_bench_image.sh
```

Set `default_docker_image: arena-bench:1` in a pack manifest, or set `docker_image` on an individual case. The executor does not pull missing images automatically.

## Reports and dashboard

```bash
arena audit-report runs/ --output docs/reports/audit-v1-results.md
arena serve

cd dashboard
npm install
npm run dev
```

See [docs/DEMO.md](docs/DEMO.md) for a fresh-clone walkthrough.

## Integrity model

The harness treats reviewer output and benchmark packs as untrusted input.

- Pack paths, schemas, and raw input sizes are validated before use.
- Unsafe patch paths and protected-file changes are rejected.
- Docker runs use bounded resources and no network access.
- Every run records its pack checksum, configuration, timings, and execution metadata.
- Only complete Docker-backed runs with an externally verified pack digest are included in the default leaderboard.

See [SECURITY.md](SECURITY.md) for the security model and reporting instructions.

## Development

```bash
make check
cd dashboard && npm run build
```

## Limitations

- The included packs are curated and small.
- Concept matching and structural validators are deterministic heuristics.
- Passing tests is evidence under the tested conditions, not proof of complete correctness.
- This is a local evaluation harness, not a public ranking service.

More detail is available in [docs/](docs/README.md).

## License

MIT. See [LICENSE](LICENSE).
