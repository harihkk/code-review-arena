# Trusted Evaluation Architecture (v0.2; Phase 1A and 1B landed, 1C/1D pending)

This is the living design document for the v0.2 milestone. The goal is not "no bugs";
it is enforceable invariants so that any unknown, incomplete, tampered, or untrusted
state is represented as `unknown` / `inconclusive` / `unverified` / `invalid`, never as a
successful or verified result. It is updated as each phase lands.

## Threat model

Benchmark packs and reviewers are both treated as adversarial.

- A pack may contain crafted path fields, symlinks/special files, hidden files, oversized
  inputs, or a `reference.patch` that targets protected files.
- A reviewer may try to read the oracle (reference patch, tests, ground truth), hardcode
  by case id, escape the workspace, exhaust memory/CPU, spawn descendants, exceed budgets,
  or emit malformed output.
- A caller may submit a self-asserted "verified" result or alter evidence after the fact.

The development machine is constrained (no model inference or heavy parallel work locally;
those belong in CI). Local gate = ruff check + ruff format --check + mypy + pytest + pack
validation + contamination check.

## Trust levels (target)

`development` < `self_reported` < `reproducible` < `official_verified`. Trust is computed
from explicit facts and returns reason codes, never inferred from a single boolean. Today
everything the repo produces is at most `self_reported`, because the reviewer process is
not isolated from the oracle (see Reviewer boundary). The public packs ship their own
`reference.patch` and stable case ids, so they are development packs, not a basis for
official rankings.

## Invariants (target, by phase)

- Pack boundary: every pack-supplied path is a validated relative path contained in its
  declared root; execution runs only from an immutable, fully hashed snapshot, never the
  mutable source directory.
- Run validity: `complete` requires zero failed, zero skipped, completed == eligible, and
  every required execution conclusive; coverage = completed / eligible.
- Reviewer boundary: an isolated reviewer receives only the blinded payload (opaque id,
  diff, required source files) and cannot read the repo, packs, tests, or reference patch.
- Execution boundary: a reproducible run records the exact harness commit, pack digest,
  and container image digest; mutable tags are not a trust identity.
- Result attestation: official results require an approved evaluator signature; a caller
  cannot self-assert `official_verified`.

## Boundaries (filled in as phases land)

- Pack boundary: Phase 1. Phase 1A (strict portable paths/ids) and Phase 1B (strict
  bounded external schemas, pre-parse byte limits, bounded YAML/JSON structure, exact
  reviewer-output contract with development-only salvage, contextual reviewer-path
  admission, comparability metadata) have landed. The immutable snapshot is Phase 1C.
- Run validity: Phase 2.
- Reviewer boundary: Phase 3.
- Execution boundary: Phase 4.
- Result attestation boundary: Phases 4 and 6.

## Deferred limitations (honest, current state)

- No reviewer isolation yet: `custom-command` runs from the repo cwd with the full host
  environment and can read `reference.patch`. All current results are self-reported.
- No held-out official packs; public packs contain their own answers.
- Docker "verified path" is documented but not exercised end to end in CI.
- Per-bug repair attribution is suite-level (overstated for multi-bug cases).
- Phase 1B bounds individual input bytes and parsed YAML/JSON structure, but does NOT
  solve filesystem time-of-check/time-of-use or provide immutable traversal: validation
  and hashing still read the mutable source and execution re-reads it later. Total
  filesystem entry-count limits and collision rejection on a snapshot remain Phase 1C;
  Git-authoritative patch application remains Phase 1D.

---

## Phase 1: Strict pack boundary and immutable snapshot

### Verification matrix (current code, before changes)

| Claim | Verified | Location |
|---|---|---|
| Pack path fields are raw `str`, not a contained type | yes | `arena/core/models.py` GroundTruthFile.path:41, AcceptableFinding.path:63, CaseInput.before_dir/after_dir/tests_dir:101-103, ValidationConfig.protected_paths:140 |
| Only `BenchmarkCase` sets `extra="forbid"`; nested models accept unknown keys | yes | `arena/core/models.py:152` is the only `ConfigDict(extra="forbid")` |
| Pack hash excludes every dotfile/dotdir, so hidden files do not change the digest | yes | `arena/benchmark/pack_hash.py` `_content_files` skips `part.startswith(".")` |
| No immutable snapshot: validation/hash run on the live source, execution re-reads it (TOCTOU) | yes | `pack_checksum`/`load_cases` read the source dir; executors copy from it later |
| Protected-path enforcement rests on the handwritten `+++` parser | yes | `arena/patching/patch_parser.py` `touched_files` parses `+++` only |

### Fields moving to `SafeRelativePath`

`CaseInput.diff`, `CaseInput.before_dir`, `CaseInput.after_dir`, `CaseInput.tests_dir`,
`GroundTruthFile.path`, `AcceptableFinding.path`, `ValidationConfig.protected_paths` (each
element), and any future oracle/patch-allowlist path.

### `SafeRelativePath` rejects

empty paths; absolute POSIX paths; Windows drive (`C:`) and UNC (`\\server`) paths; `.`
and `..` components; backslash separators; NUL and other control characters; Unicode
separator/space lookalikes that could change interpretation under normalization. Containment
against the declared root resolves the root first (never an already-escaped path).

### Pack snapshot data flow (target)

`source dir -> snapshot_pack(source) -> immutable PackSnapshot (regular files only, links/
special rejected, metadata rechecked before/after copy, every file hashed except the
checksum artifact, size/count bounded, validated) -> all loading / certification / mutation
/ scoring / execution read ONLY the snapshot -> snapshot cleaned at end`. We never hash one
tree and execute another.

### Patch enforcement (target)

Make the post-application git tree authoritative rather than the handwritten parser: init a
temp git repo on the baseline, `git apply --check`, apply atomically (no partial `--reject`
for scoring), read actual changed/added/renamed/deleted paths via NUL-delimited git output,
validate each with `SafeRelativePath`, reject protected-file changes and unsafe modes on the
resulting tree, rescan the workspace, and on any violation discard the whole workspace with
a structured reason. The same pipeline applies to candidate, reference, alternate-valid, and
known-wrong patches.

### Files expected to change

`arena/security/paths.py` (SafeRelativePath type + strengthened validators), `arena/core/
models.py` (apply the type; strict-schema base in the schema sub-step), `arena/benchmark/
pack_hash.py` and a new `arena/benchmark/snapshot.py` (immutable snapshot), `arena/benchmark/
case_loader.py` and `certify.py` and `mutation.py` and `benchmark_runner.py` (load/execute
from the snapshot), `arena/patching/patch_applier.py` and `patch_parser.py` (git-result
patch pipeline), and new tests under `tests/`.

### Test matrix (adversarial + property)

traversal in every path field; absolute POSIX and Windows paths; UNC; quoted git paths;
escaped spaces/tabs/quotes/non-ASCII filenames; rename/copy into protected paths; delete and
recreate protected paths; symlink and gitlink modes; case-only filename collisions; Unicode
normalization collisions; hidden executable files; concurrent replacement during snapshot;
source modified after snapshot; reference patch violating candidate-patch policy. Property
tests fuzz path and diff parsing.

### Path policy (decided)

Portable ASCII profile only: ASCII letters, digits, `_`, `-`, `.`, `/`. No empty,
`.`, or `..` components; no leading/trailing slash; no backslash; no colon; no
component ending in a dot or space; Windows reserved device names rejected
case-insensitively including with an extension (NUL.txt); max total path length
1024, max component length 255. Unicode filenames are NOT supported in pack paths;
this removes confusable/normalization attack classes by construction rather than
blacklisting examples. Case-insensitive and Unicode-normalization COLLISIONS (two
distinct paths that collide on a case-insensitive or NFC filesystem) are enforced
again at snapshot construction in Phase 1C.

Error integration: the Pydantic-facing validators (`SafeRelativePath`, `SafeCaseId`)
raise `ValueError`, so a bad value is a normal Pydantic error with an accurate field
location (e.g. `input.after_dir`, `ground_truth.bugs.0.files.0.path`,
`validation.protected_paths.0`). Domain wrappers (`validate_relative_path`,
`validate_case_id`) translate to Arena's `ValidationError` for filesystem callers.

### Increment status

- 1A strict portable pack paths + case ids at the schema boundary: DONE.
  One shared `_component_error` validator underpins both `SafeRelativePath` and
  `SafeCaseId`, so a case id (which becomes a directory name) gets the exact same
  portable-component policy as a path segment: ASCII profile, no separators, no
  reserved device names even with an extension (NUL.txt), no trailing dot or space,
  bounded length, exactly one component. Applied to `GroundTruthFile.path`,
  `AcceptableFinding.path`, `CaseInput.{diff,before_dir,after_dir,tests_dir}`,
  `ValidationConfig.protected_paths`, `BenchmarkCase.id`, and `CaseManifest.cases`
  (with duplicate-id rejection). `load_cases` enforces the identity invariant
  (manifest id == directory name == `BenchmarkCase.id`) and rejects case-insensitive
  id collisions. Adversarial parametrized suite + Pydantic-location regression +
  property-based (hypothesis) suite + TypeAdapter/JSON/YAML/round-trip/schema/optional/
  default tests + loader identity/collision regressions. Packs load and validate,
  contamination clean, full gate green (333 passed, 4 skipped).
  Total-path-length policy: 1024 chars total, 255 per component (128 for a case id).
  These are feasibility bounds, not the final word: Phase 1C re-checks case-insensitive
  and Unicode-normalization COLLISIONS and real filesystem feasibility on the snapshot.

  Checksum-coverage invariant (added): the pack checksum currently excludes
  dot-prefixed components and `__pycache__`, so content there is not covered by the
  digest and could be swapped silently. Until Phase 1C snapshot hashing covers every
  regular file, (a) no path component or case id may start with a dot, and a case id
  must additionally start with an ASCII alphanumeric (no leading `_`/`-`); and (b)
  `validate_dataset`/`load_and_validate_pack` FAIL CLOSED on any file the checksum omits
  (`pack_hash.unhashable_content`). The checksum exclusion is the root artifact only
  (`relative == pack.sha256`): a nested `<case>/after/pack.sha256` is ordinary pack
  content and is covered by the digest. The four vestigial `.gitkeep` placeholders in `v1`
  (empty `tests/` dirs of `run_tests: false` cases) were removed to satisfy this; they
  were already outside the digest, so the checksum is unchanged. This admission guard is
  removed in Phase 1C once snapshot hashing includes every file.
- 1B strict, bounded external contracts: DONE (see "Phase 1B" below for the full
  reviewer-output contract). Every external nested model inherits a strict base
  (`extra="forbid"`, `strict=True`, `validate_default=True`, `allow_inf_nan=False`); pack,
  reviewer-output, and API-request models all reject unknown fields, type coercion, and
  NaN/inf. Raw byte ceilings are enforced before any YAML/JSON/diff/patch parsing and at
  the ASGI request-body boundary; YAML parsing additionally forbids aliases and duplicate
  keys and bounds depth/node count; collection, string, numeric (dedicated domain limits),
  and identity/uniqueness bounds are enforced. A coherent minimum-dependency CI job
  (Python 3.11, FastAPI 0.110, Pydantic 2.6, HTTPX 0.27) guards the declared floors.
- 1C immutable pack snapshot + rewire load/cert/mutation/exec to the snapshot, including
  case-insensitive / normalization collision rejection: pending.
- 1D git-result patch pipeline (temp repo + git apply --check + NUL-delimited paths):
  pending.

---

## Phase 1B: strict external contracts and the reviewer-output contract

### Strict external schemas

Every externally controlled nested model (pack files, reviewer output, API requests)
inherits `_StrictExternal` (`ConfigDict(extra="forbid", strict=True,
validate_default=True, allow_inf_nan=False)`). Strictness does not propagate in Pydantic,
so each nested model inherits it explicitly. Consequences: unknown fields fail, string ->
number / string -> bool coercion fails, defaults are validated, and `NaN`/`Infinity`
fail. Collections are bounded and reject exact duplicates where duplicates cannot add
meaning (bug concepts, must_mention, fix keywords, stack, line ranges, acceptable
findings, protected paths, structural validators); a manifest must contain at least one
case; bug ids are unique after auto-assignment (case-fold included); argv command/token
counts are bounded; numeric fields use dedicated domain limits (score weight 0..100,
penalties 0..100, beta >0..100, timeouts/wall-time/cost), not a reused magnitude cap.
`BenchmarkCase.case_dir` is internal runtime state and is rejected from pack input.

### Raw byte and structure limits

`core/limits.py` centralizes documented operational-safety bounds. Raw byte ceilings are
checked BEFORE parsing for `manifest.yaml`, `case.yaml`, `pr.diff`, `reference.patch`,
ground-truth/source reads, HTTP reviewer responses (on the decoded body, streamed, so a
compressed bomb cannot bypass it; Content-Length is not authoritative), custom-command
output (truncated output is never parsed), and the API request body (a pure ASGI
middleware buffers at most limit+1 bytes and returns 413 before the route runs). YAML
parsing forbids aliases and duplicate keys and bounds depth/node count; the strict JSON
decoder rejects duplicate keys, `NaN`/`Infinity`/`-Infinity`, exponent-overflow
non-finite floats, and excessive depth/node count. These bound memory and parser
amplification only; they do not solve filesystem TOCTOU or immutable traversal (Phase 1C),
and patch semantics remain Phase 1D.

### Reviewer-output contract

Exact is the default comparable contract. The raw response must be exactly one strict
JSON object that validates as `ReviewResult`, with every finding path admitted. The
default parser performs NO tolerant transformation: no Markdown-fence stripping, brace
extraction, trailing-comma removal, bare-list wrapping, field insertion, or finding
dropping. Fenced, prose-wrapped, trailing-comma, bare-list, unknown-field,
one-invalid-finding, duplicate-key, and non-finite inputs are all `invalid`.

Parse status is one of `exact`, `tolerant`, `repaired`, `invalid`:

- `exact` and `invalid` are comparable. `invalid` is a legitimate reviewer-contract
  failure that still scores (it takes the invalid-output penalty); it does not make a run
  untrusted or non-comparable.
- `tolerant` and `repaired` are produced only by development-only salvage
  (`--enable-repair`) and make the run NON-COMPARABLE by default.

Salvage, when enabled, tries exact, then documented tolerant transforms
(`strip_markdown_fence`, `extract_json_object`, `remove_trailing_commas` -- a string-aware
scanner that never touches commas inside string content), then deterministic repair
(`wrap_findings_list`, `default_overall_risk`, `default_review_summary`,
`drop_invalid_findings`). Repair never invents a findings list: a top-level list may be
wrapped, but a dict must explicitly carry `findings` as a JSON array; a missing/null/
non-list `findings` stays invalid. Salvage never calls a model and never relaxes strict
decoding (duplicate keys and non-finite numbers stay rejected). The raw response is always
retained.

Parse evidence is persisted on `ReviewerResponse`: `parse_status`, `parse_actions` (fixed
vocabulary, bounded), `input_finding_count`/`retained_finding_count` (`int | None`),
`dropped_finding_count`, and a bounded `parse_error_summary` that never echoes the full
output. New responses satisfy invariants (invalid has no parsed result or retained
findings; exact has one attempt, no actions, no drops; tolerant records actions and drops
nothing; repaired records an action and satisfies input = retained + dropped).

### Reviewer-path admission

`Finding.file` is reviewer-controlled. A leading `./` is removed and the remainder must
satisfy the same portable relative-path policy as pack paths. A Git `a/`/`b/` prefix is
resolved only against the reviewer-visible known paths (relevant-file keys plus
diff-referenced paths, never ground truth): complete-known keeps the complete path,
stripped-known uses the stripped path, both-known is rejected as ambiguous, neither-known
keeps the complete path, and with no context the prefix is never stripped. A real
top-level `a/` or `b/` directory is therefore not corrupted. The canonical path is stored
on the parsed finding; the raw response keeps the original.

### Comparability and legacy compatibility

`RunMetadata` carries `reviewer_parse_status_counts` and a fail-closed
`non_exact_output_used` (False when every case is exact or invalid, True when any case was
salvaged, None for old runs). The single leaderboard eligibility policy (file and database)
additionally requires `non_exact_output_used is False` by default; True and None are
non-comparable by default but visible with `--include-unverified`. This rides in the
stored run JSON, so `RUN_SCHEMA_VERSION` is unchanged and no SQL migration is needed. Old
saved runs and reviewer responses load unchanged: a response without `parse_status` derives
it from `invalid_output`/`parse_attempts` and loads with unknown (None) counts rather than
fabricated evidence; a run with `non_exact_output_used: null` is treated as legacy/unknown.
