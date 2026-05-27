# Architecture

Code Review Arena is a backend-first evaluation harness. A benchmark fixture contains only
inputs visible to a reviewer plus separately loaded ground truth. `BenchmarkRunner` loads a
fixture, calls a reviewer, and sends structured findings to both the review-quality scorer
and, in full mode, the deterministic patch-validation pipeline.

## Module boundaries

| Module | Responsibility |
|---|---|
| `arena.core` | Typed contracts, configuration, errors, reviewer registry |
| `arena.benchmark` | Manifest/case loading, diff parsing, validation, orchestration |
| `arena.reviewers` | Prompting, JSON parsing, provider and mock adapters |
| `arena.tools` / `arena.execution` | Controlled evidence gathering in materialized trees |
| `arena.scoring` | Localization, concept/fix/severity scoring and false positives |
| `arena.patching` | Isolated patch workspace creation and unified-diff application |
| `arena.validators` | Tolerant structural checks for acceptable repair shapes |
| `arena.reports` | Portable JSON, readable Markdown, standalone HTML and leaderboard |
| `arena.storage` | SQLite schema and repository operations |
| `arena.server` | FastAPI endpoints used by the dashboard |

## Dashboard

The Next.js app reads only API representations. The leaderboard ranks patch/full runs by
`validated_f_beta` while exposing `detection_f_beta` separately. A run page summarizes
the validation funnel and failure reasons, and the case trace page renders the diff
alongside findings, raw patch, post-patch execution and validator results.

## Trust boundary

Ground truth never enters `CaseContext` prompt rendering. Reviewer patches are applied only
to `runs/<run-id>/workspaces/<case-id>/`, never to benchmark fixtures. Local execution is
disabled unless explicitly enabled; cases may instead identify a Docker image.

## Reproducibility

Each report records reviewer/model, prompt version, benchmark version, temperature, commit
hash where available, timestamps, raw and parsed output, per-case breakdown, latency and
estimated cost, raw suggested patches, test output tails and validator evidence.

## Deployment

Docker Compose starts the API, dashboard and an optional Postgres service for future
advanced storage mode. The current API uses a mounted SQLite database and mounted report
directory for local reproducibility. The dashboard image is built as a minimal Next.js
standalone runtime and waits for the API health check before startup.
