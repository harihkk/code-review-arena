# GitHub Action Audit Mode

The repository includes an audit workflow that runs the key-free deterministic patch
baseline in continuous integration. It validates fixtures, executes the full-mode mock
reviewer, ranks results with `validated_f_beta`, and uploads run reports as an artifact.

```yaml
- run: python -m pip install -e ".[dev]"
- run: arena validate benchmark_sets/v1
- run: arena run benchmark_sets/v1 --reviewer mock:perfect_patch --mode full --allow-local-execution
- run: arena leaderboard runs/ --metric validated_f_beta --beta 1.0
```

Teams can adapt this harness to evaluate an internal reviewer locally or in controlled
CI. Provider-backed reviewers should be invoked deliberately with secrets and budget
controls; the supplied audit baseline requires no external model credentials.
