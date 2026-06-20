# Trusted Evaluation Architecture (v0.2, in progress)

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

- Pack boundary: Phase 1 (this phase).
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
  (`pack_hash.unhashable_content`). The four vestigial `.gitkeep` placeholders in `v1`
  (empty `tests/` dirs of `run_tests: false` cases) were removed to satisfy this; they
  were already outside the digest, so the checksum is unchanged. This admission guard is
  removed in Phase 1C once snapshot hashing includes every file.
- 1B strict external schemas (extra=forbid + size/count limits): pending. The strict base
  must set `validate_default=True`. Apply strict forbid to pack and API-request models.
  Reviewer-output models (Finding/ReviewResult) also use `extra="forbid"`, but an unknown
  field there must degrade to INVALID OUTPUT (not a crash, not silent accept); a relaxed
  parser may exist only as a clearly labeled development mode that makes the run ineligible
  for comparable trust.
- 1C immutable pack snapshot + rewire load/cert/mutation/exec to the snapshot, including
  case-insensitive / normalization collision rejection: pending.
- 1D git-result patch pipeline (temp repo + git apply --check + NUL-delimited paths):
  pending.
