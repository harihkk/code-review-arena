# Audit Report

`arena audit-report` aggregates real `audit_v1` run JSON from `runs/` and writes:

- Markdown report (default: `docs/reports/audit-v1-results.md`)
- Dashboard JSON (default: `dashboard/public/reports/audit-v1.json`)

```bash
arena audit-report runs/ --output docs/reports/audit-v1-results.md
```

The command never invents metrics. When no `audit_v1` runs exist, it writes a clear empty-state report.

## Sections

1. Summary
2. Methodology
3. Reviewer comparison (`detection_f_beta` vs `validated_f_beta`)
4. Detection vs validation gap
5. Failure mode breakdown
6. Case studies (up to three failing examples)
7. Reproducibility commands
8. Limitations

View the rendered dashboard page at `/reports/audit-v1` after generating the JSON file.
