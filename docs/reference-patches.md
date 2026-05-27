# Reference Patches

Every `audit_v1` case includes a `reference.patch` file containing a canonical known-good
fix for the buggy `after/` tree. The patch is stored as an inspectable unified diff and is
expected to apply cleanly, pass required regression tests, and satisfy structural
validators.

`reference-patch` reads these static artifacts directly. It validates the benchmark
fixtures and execution pipeline without inventing a reviewer result.

`mock:perfect_patch` is different: it is a deterministic mock-reviewer happy path that
produces valid fixes through reviewer plumbing. The two controls should reach the same
validated outcome for different reasons.

```bash
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena run benchmark_sets/audit_v1 --reviewer mock:perfect_patch --mode full --allow-local-execution
```
