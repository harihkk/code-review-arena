# Custom Command Reviewer

The `custom-command` reviewer lets you benchmark external, private, or local review agents
without writing a Python adapter.

## Example

```bash
arena run benchmark_sets/audit_v1 \
  --reviewer custom-command \
  --command "python scripts/fake_reviewer.py --case {case_json}" \
  --mode full \
  --allow-local-execution \
  --reviewer-timeout-seconds 120
```

## Reviewer-visible JSON

Arena writes a temporary `case.json` containing only:

- case metadata (`case_id`, `title`, `category`, `severity`, `stack`, `description`)
- `pr_diff`
- `relevant_files`
- optional `test_output` / `static_analysis_output`

Ground truth, scoring weights, validator names, and expected line ranges are never included.

## Placeholders

| Placeholder | Value |
|---|---|
| `{case_json}` | Path to serialized reviewer JSON |
| `{diff_file}` | Path to the PR diff file |
| `{case_id}` | Case identifier |
| `{workspace}` | Temporary directory containing copied relevant files |

Commands are parsed with `shlex.split` and executed with `subprocess.run(..., shell=False)`.

## Output contract

Stdout must contain a single JSON document matching the standard `ReviewResult` schema.
Nonzero exits, timeouts, and invalid JSON are recorded as structured invalid reviewer output.
