# Benchmark Design

Version `v1` contains ten single-primary-bug pull requests. Cases are minimal enough to
inspect but preserve realistic application idioms: dependencies, serializers, cache keys,
database scoping, asynchronous mutation and retrieval-grounding checks.

A case is useful when the bug is behaviorally meaningful, precisely localizable in the PR
diff, and supported by either a regression test or a clear ground-truth explanation.

