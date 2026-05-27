# Troubleshooting

## `arena` command not found

Create an environment, activate it, and install the package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## `pytest` not found or the virtual environment is not activated

Run `source .venv/bin/activate`, then confirm `which arena` and `which pytest` resolve
inside `.venv`.

## npm dependencies missing

```bash
cd dashboard
npm install
npm run build
```

## Stale Docker containers

Stop old services with `docker compose down`, then run `docker compose up --build`.

## API healthy but dashboard stale

Restart the dashboard development server. The audit report and verification pages use
generated JSON, so regenerate their snapshots after new runs:

```bash
arena audit-report runs/ --output docs/reports/audit-v1-results.md
python scripts/generate_verification_snapshot.py --generate-report
```

## Audit report missing

Generate at least one `audit_v1` run and then build its report:

```bash
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena audit-report runs/ --output docs/reports/audit-v1-results.md
```

## No runs shown

API-backed run pages read the configured SQLite database. Produce a run and ensure
`arena serve` is using that same local workspace. Static `/reports/audit-v1` and
`/verify` pages read generated JSON snapshots instead.
