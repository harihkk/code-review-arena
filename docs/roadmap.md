# Roadmap

Container-isolated test execution shipped: cases run in a locked-down Docker
sandbox with the hidden tests mounted read-only (see the Docker backend in the
README). What remains:

- Expanding the benchmark to a larger, certified case set across more stacks
- Tool-use traces and an iterative agent review mode
- Per-bug oracle attribution for multi-bug cases
- Native GitHub pull-request ingestion and public result exports
- Full dashboard filtering, comparisons, and diff annotations
