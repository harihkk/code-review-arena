# RealFix Pilot v1

**Status: partial methodology increment — 3 execution-verified cases, not the full 12-case target.**

This pilot converts real, historical bug fixes from mature open-source Python
projects into execution-verified Code Review Arena cases using the merged
deterministic importer (`arena import-fix`) and the existing Docker certification
ladder. Every case here reached the `verified` level through Docker.

These are **synthetic reverse-review cases derived from real fixes**: the buggy
tree is the source *before* the historical repair and the synthetic `pr.diff` is
the inverse of the real change. They are **not** the original bug-introducing pull
requests. They are review exercises whose ground truth is anchored in a real
defect, a real maintainer fix, and a real regression test.

This is a **methodology pilot, not the final paper-scale benchmark.** With only 3
cases it supports no statistical conclusions about reviewer performance.

## Accepted cases (3)

| case_id | repo | license | category | severity | src file(s) | test command | changed src LOC | baseline | reference | mutants | kill | determinism | level |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| attrs_frozen_error_message_001 | python-attrs/attrs | MIT | correctness | low | src/attr/exceptions.py | test_functional.py::TestFunctional::test_frozen_instance | 8 | fails | passes | 0 viable | n/a | 3 runs | verified |
| click_shared_default_precedence_001 | pallets/click | BSD-3-Clause | correctness | medium | src/click/core.py | test_defaults.py | 16 | fails (exit 1) | passes | 20 | 55% | 3 runs | verified |
| rich_table_padding_width_001 | Textualize/rich | MIT | correctness | low | rich/table.py | test_table.py + test_columns.py | 16 | fails | passes | 20 | 80% | 3 runs | verified |

Full per-case evidence (repository URL, license URL, buggy/fixed commit ids,
issue/PR, selectors, changed paths, why the defect is wrong, which regression test
exercises it, why the ground truth is supported) is committed under
`benchmark_sources/realfix_pilot_v1/<case-id>/evidence.yaml`.

## Candidate pool and admission

- Candidates screened: **25** (across pallets/click, pallets/jinja, pallets/markupsafe, python-attrs/attrs, Textualize/rich).
- Accepted: **3**. Rejected: **22**.
- The deterministic accept/reject registry is `realfix-pilot-v1-rejections.jsonl`.

Rejection reasons observed: `unrelated_changes` (the fix commit also touches
CHANGES/docs/lint, which the importer cannot classify), `no_clear_bug_evidence`
(feature/rework/typo/no linked issue), `test_only`, `flaky` (race-condition fix).

### Key methodology finding: changelog-bundling friction

The importer (correctly, by design) requires **every** path changed between the
buggy and fixed commits to fall under a declared source selector or the tests
root. Mature projects almost always bundle a `CHANGES.rst`/changelog or docs edit
into the same commit as the fix, which makes that commit unimportable as-is. Only
"clean" commits whose entire diff is source + tests are usable, and those are rare
(e.g. Click had ~4 clean bug-fix commits since 2025-09-01; Jinja and MarkupSafe
had none). This is the dominant reason the accepted yield is far below 12, and it
is the main thing a larger RealFix effort must plan around (screen far more repos,
or split fix vs. changelog commits). It was **not** worked around by modifying the
importer.

## Distributions (accepted cases)

- Repositories: pallets/click (1), python-attrs/attrs (1), Textualize/rich (1) — 3 distinct repos.
- Licenses: MIT (2), BSD-3-Clause (1).
- Categories: correctness (3). *(Single category — below the diversity target.)*
- Commit dates: 2025-09-22, 2026-01-23, 2026-03-14 — **3/3 on or after 2025-09-01**; none before 2025-01-01.
- Diff size: all three are **small** (< 30 changed source lines: 8, 16, 16). No medium or substantial fixes were admitted in this increment.

## Docker environment

- Image tag: `arena-realfix-pilot:1` (built from `docker/realfix_pilot/`).
- Local image id: `sha256:d0ba1bfaed1e0c292df781c51661187d457f4d86b6728a600da61afb04b61ed4`.
- Base: `python:3.11-slim` (Python 3.11.15). Pinned: `pytest==8.3.5`, `hypothesis==6.140.3` (hypothesis is only an import-time dependency of attrs' test module; no property-based test is exercised). `PYTHONPATH=/workspace/src` makes src-layout packages importable from the materialized source.
- No Arena source, no repository checkout, no network at test time (`--network none`), no credentials, no mutable installation during a run.

## Certification (Docker)

`arena certify-pack benchmark_sets/realfix_pilot_v1 --limit 20 --determinism-runs 3`
→ pack level **verified**; all 3 cases `verified`.

- Mutation: click 55% (20 mutants), rich 80% (20 mutants), attrs 0 viable mutants
  (the change is too small to mutate; the case rests on baseline-fails +
  reference-passes + determinism, which is how the existing ladder treats
  zero-viable-mutant cases).
- Determinism: baseline-fails / reference-passes held across 3 runs each.
- Deterministic rebuild: re-importing all three cases reproduces byte-identical
  case directories; the pack checksum is idempotent.

## Control runs (Docker, full mode)

| reviewer | validated repair |
|---|---|
| reference-patch | 3 / 3 |
| control:perfect_patch | 0 / 3 |
| control:bad_patch | 0 / 3 |
| control:keyword_gamer | 0 / 3 |
| control:detects_no_patch | 0 / 3 |
| control:malformed_patch | 0 / 3 |

`reference-patch` (apply the gold patch) validates 3/3 — the meaningful
perfect-patch control for new cases. The failure controls all validate 0/3, and
keyword-gamer obtains no validated repair through keyword matching, as required.

Note: `control:perfect_patch`, `control:bad_patch` and `control:keyword_gamer` are
fixture oracles keyed to the bespoke `v1`/`audit_*` case ids; they have no answer
for new real cases and therefore produce no patch (0/3). This is a property of
those control reviewers, not of the pilot cases, and was not worked around by
changing production code. `reference-patch` is the correct general perfect-patch
control here.

## Pack integrity

- `pack.sha256`: `0333e046a7a8a2d22ad09a5108663c3a1ec9b4ad8c29beabb5c5d3379ff400de`
- Case ids are disjoint from `v1`, `audit_v1`, `audit_v2`; the shipped packs are
  byte-for-byte unchanged.

## Limitations

- **Count:** 3 verified cases, not 12. Admission standards were not lowered to
  reach a number; the changelog-bundling friction and the mutation-adequacy bar
  limited the clean, certifiable yield in this session.
- **Diversity:** single category (correctness), all small fixes, 3 repos, 2
  licenses — below the size/category/repo-count targets for the full pilot.
- **attrs case** has zero viable mutants, so its strength rests on the
  deterministic baseline-fails/reference-passes verdict rather than mutation.
- **Controls:** the fixture-bound perfect/bad/keyword controls do not generalize
  to new cases; `reference-patch` is used as the general perfect-patch oracle.
- This is a methodology pilot. It is not paper-scale and supports no statistical
  conclusions about model performance.
