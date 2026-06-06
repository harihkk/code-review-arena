# Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request. It mirrors the local
commands, so a green checkout matches a green CI run. No credentials are required; the
controls are deterministic.

The backend job:

```yaml
- run: python -m pip install -e ".[dev]"
- run: ruff check arena tests && ruff format --check arena tests
- run: mypy arena
- run: pytest
- run: arena validate benchmark_sets/v1 && arena validate benchmark_sets/audit_v1
- run: arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
- run: arena leaderboard runs/ --metric validated_f_beta --beta 1.0
```

A second job builds the dashboard (`npm ci` then `npm run build`). To benchmark your own
reviewer in CI, add a step that runs `arena run ... --reviewer custom-command --command "..."`.
