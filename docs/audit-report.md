# Audit Report

`arena audit-report` aggregates real run JSON from `runs/` for a benchmark pack and writes:

- Markdown report (default: `docs/reports/audit-v1-results.md`)
- Dashboard JSON (default: `dashboard/public/reports/audit-v1.json`)

It defaults to `audit_v1`; pass `--benchmark-set` to aggregate another pack (and point
`--json-output` at that pack's dashboard file):

```bash
arena audit-report runs/ --output docs/reports/audit-v1-results.md
arena audit-report runs/ --benchmark-set audit_v2 \
  --output docs/reports/audit-v2-results.md \
  --json-output dashboard/public/reports/audit-v2.json
```

The command never invents metrics. When no runs for the pack exist, it writes a clear empty-state report.

## Sections

1. Summary
2. Methodology
3. Reviewer comparison (`detection_f_beta` vs `validated_case_rate`)
4. Detection vs validation gap
5. Failure mode breakdown
6. Case studies (up to three failing examples)
7. Reproducibility commands
8. Limitations

View the rendered dashboard page at `/reports/audit-v1` after generating the JSON file.
