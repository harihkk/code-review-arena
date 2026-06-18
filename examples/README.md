# Examples

Committed sample output, generated from the deterministic `control:perfect` baseline on
benchmark set `v1`:

- `sample_run.json`: machine-readable run trace
- `reports/control-perfect-report.md`: readable case-by-case report
- `reports/control-perfect-report.html`: standalone visual report

Regenerate them by running a perfect control benchmark and rendering its latest run
through the report writers:

```bash
arena run benchmark_sets/v1 --reviewer control:perfect
# then copy runs/<latest>/run.json, report.md, and report.html into examples/
```
