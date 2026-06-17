# Code Review Arena - v2 Architecture & Migration Plan

Status: design of record for the v2 rebuild. This document is written *before*
the code so that every later change has a precise target. It is grounded in the
current implementation (file:line references are to the tree at the time of
writing) rather than aspiration.

---

## 1. Identity and non-goals

Arena is **not** an AI code reviewer. It does not review the user's pull
requests. It is the independent, local-first **evaluation and red-team
laboratory** for *other* reviewers and agents.

The product promise: **"Find out which AI code-review findings survive
execution."**

For any reviewer under test, Arena answers, with inspectable evidence:

1. Did it independently find the real defects?
2. Did it localize and explain them correctly?
3. Did it make unsupported, duplicate, vague, or exaggerated claims?
4. Did it produce one complete repair for the case?
5. Did that repair fix *all* required defects without regressions?
6. Did it tamper with tests, exploit leaked clues, or otherwise game the run?
7. What exact evidence backs every number?

Non-goals (explicitly out of scope): review generation, paid-provider-first UX,
hosted model serving, multi-tenant SaaS, Kubernetes, billing, orgs/permissions.

---

## 2. Locked decisions

- **Docker is the standard execution backend** for normal, verified,
  publishable, and leaderboard runs. No silent Docker→local fallback; fail
  clearly when Docker is absent.
- **Trusted-local** execution exists only behind an explicit development
  override and is **never** leaderboard-eligible.
- **Free and local-first.** No paid-provider SDK is required or promoted.
  Reviewer integration is **local command** and **generic HTTP /
  OpenAI-compatible local endpoints** (Ollama, LM Studio, vLLM, llama.cpp).
- **The bundled demo runs fully offline**, no API key, no usage cost.
- **Existing pre-v2 runs are preserved as legacy** and excluded from v2
  comparisons. New metrics are never fabricated from data legacy runs never
  recorded.
- **No AI attribution** anywhere: commit messages, files, comments, authorship
  trailers.

---

## 3. Current-state audit (verified)

These are confirmed against the code, not assumed:

| Area | Issue | Location |
| --- | --- | --- |
| Patch selection | Only the patch attached to `matched_bug_index == 0` (or first TP finding) is applied; multi-bug repairs collapse to one. | `arena/benchmark/benchmark_runner.py:114-120` |
| Metric units | `validated_precision = precision(case-level validated_tp, finding-level fp)` mixes units. | `arena/scoring/deterministic_scorer.py:98-101` |
| Detection completeness | "Detected" means `bug_found` (>= 1), never "all bugs". | `arena/scoring/deterministic_scorer.py:40` |
| Run validity | Skipped cases recorded, but metrics aggregate completed cases only; no run status / coverage; partial run still yields a headline number. | `arena/benchmark/benchmark_runner.py:282-350` |
| Budgets | Wall/cost checked only between cases; one case can exceed the whole budget. | `arena/benchmark/benchmark_runner.py:283-293` |
| Process lifecycle | `subprocess.run(timeout=...)` everywhere; no process group, no tree-kill; orphans survive timeout. | `arena/execution/test_executor.py:137`, `arena/patching/patch_applier.py:99` |
| Docker hardening | `docker run` uses only `--rm -v -w -e`; no network/caps/limits/digest; silent fallback to local. | `arena/execution/test_executor.py:104-118`, `:55-61` |
| Test integrity | Hidden tests copied into the writable patched workspace. | `arena/benchmark/benchmark_runner.py:137-141` |
| Env exposure | `HOME` forwarded to untrusted fixtures. | `arena/execution/hardening.py:26` |
| Pack reality | Almost all shipped cases are `run_tests: false` with `docker_image: null`; only `audit_v1/security_*` execute. So "execution-backed" is currently true for a minority. | `benchmark_sets/v1/*/case.yaml` |
| Structural validators | Hand-authored heuristics block the primary validated score. | `arena/scoring/deterministic_scorer.py:53` |

Already in place (do not rebuild): pack checksum + pinning, run manifest with
secrets redacted, versioned SQLite migrations (`arena/storage/db.py`,
`SCHEMA_VERSION = 1`), multi-bug *ground truth* shape (`GroundTruth.bugs[]`),
reviewer-blind payload (`arena/benchmark/ground_truth.py`), contamination lint,
allowlisted env + rlimits for local fixtures.

---

## 4. Target design

### 4.1 Reviewer contract v2

The parsed response gains one field: a single **case-level repair**.

```
ReviewResult:
  findings: list[Finding]      # individual claims (unchanged shape + evidence_status later)
  proposed_patch: str | None   # NEW: the complete unified diff for the whole case
  overall_risk: Risk
  review_summary: str
```

Rules:
- `proposed_patch` is the **only** thing applied. Per-finding
  `Finding.suggested_patch` becomes advisory/explanatory and is **never applied**.
- No concatenation of finding patches (overlap/order/conflict is ambiguous).
- **Backward-compatible parsing, no ambiguous semantics:** if `proposed_patch`
  is absent but **exactly one** finding carries a patch, adopt it as the case
  patch (unambiguous). If `proposed_patch` is absent and **two or more** findings
  carry patches, do **not** guess - `patch_provided = False`, failure reason
  `ambiguous_patch_source`.

Each `Finding` keeps: stable id (new), title, summary, category, severity, file,
line range, evidence, confidence, optional advisory `suggested_fix`.

Integration methods: `command` reviewer (exists), new `http` reviewer
(OpenAI-compatible chat completions + a generic JSON-POST mode). No provider SDKs.

### 4.2 Ground truth, oracles, and evidence attribution

This is the differentiator and must be precise.

**Bug identity.** `GroundTruthBug` gains a required stable `id`. Legacy single-bug
cases migrate to `bugs: [{id: bug-1, ...}]`.

**Behavioral oracles.** A new first-class construct, distinct from heuristic
"structural validators":

```
Oracle:
  id: str
  name: str
  kind: behavioral | invariant | regression
  selector: str           # e.g. a pytest node id, or argv; runs in the sandbox
  bug_ids: list[str]      # which bug(s) this oracle proves
  timeout_seconds: int
```

**Attribution is by oracle→bug→finding, never by patch fragment:**
1. Match findings to ground-truth bugs (existing matcher, extended to multi-bug).
2. Apply the single case-level patch.
3. Run all oracles. A bug is **behaviorally repaired** iff every oracle mapped to
   it passes *and* (guaranteed at pack-certification time) those oracles fail on
   the buggy baseline.
4. Derive each finding's `evidence_status`:
   `supported` · `unsupported` · `correctly_localized` · `incorrectly_localized`
   · `detected_but_unrepaired` · `repair_validated` · `explanation_inconsistent`.
5. Derive the case `case_status`:
   `complete_repair` · `partial_repair` · `irrelevant_repair` (visible tests pass
   but mapped oracles for detected bugs fail) · `regression` · `tampering` ·
   `inconclusive` · `execution_validated`.

Distinguish **textual review completeness** (did findings name every bug) from
**behavioral repair completeness** (did the patch fix every bug). They are
reported separately and never collapsed.

### 4.3 Scoring - four dimensions, consistent units

The cardinal rule: **never combine units in one formula.** Units are: *bug*
(each ground-truth bug), *finding* (each reviewer claim), *case*.

**Review Accuracy**
- `detection_recall = bugs_matched / bugs_total` (bug)
- `detection_precision = supported_findings / total_findings` (finding) - standard
  IR precision-over-predictions; this pairing is conventional and unit-clean.
- `detection_f_beta` from the two above (kept; well-defined).
- `localization_accuracy = correctly_localized / bugs_matched` (bug)
- `bug_completeness_rate = cases_all_bugs_detected / cases` (case)
- `severity_calibration_error` = mean ordinal distance over matched bugs.

**Repair Success** (case + bug units only; **no finding-level FP mixed in**)
- `patch_apply_rate = applied / provided` (case)
- `validated_bug_rate = bugs_behaviorally_repaired / required_bugs` (bug)
- `validated_case_rate = fully_validated_cases / eligible_cases` (case) - fully
  validated = all required bugs repaired + required tests pass + no regression.
- `complete_repair_rate = all_required_bugs_repaired_cases / eligible_cases` (case)
- `regression_free_rate = no_regression / applied` (case)

**Review Trustworthiness** (finding + case units)
- `supported_claim_rate = supported_findings / total_findings`
- `false_positive_rate = fp_findings / total_findings`
- `unsupported_findings_per_case`, `duplicate_finding_rate`
- `overclaim_rate`, `partial_repair_rate`, `irrelevant_repair_rate`
- `gaming_rate` (from red-team + tamper signals)

**Repair Confidence** (per-case level, escalating):
- `basic` (required tests pass) → `strong` (+ behavioral/invariant oracles) →
  `adversarial` (+ mutants/counterexamples rejected) → `high` (+ differential vs
  reference + workspace integrity intact).

**`validated_f_beta` is removed** as a leaderboard metric (its units were
incoherent). The default leaderboard sort becomes `validated_case_rate`.
`detection_f_beta` remains. A single composite ranking score may exist as a
*documented, visible* weighted blend, but the components are always shown.

### 4.4 Run lifecycle and validity

```
RunStatus = complete | partial | invalid | failed | cancelled | legacy
```

`RunResult` gains: `schema_version`, `run_status`, `execution_backend`
(`docker` | `trusted-local`), `image_digest`, and coverage:
`eligible_case_count`, `completed_case_count`, `failed_case_count`,
`skipped_case_count`, `coverage_rate`.

Rules:
- `partial`, `invalid`, `failed`, `cancelled`, `legacy` runs are **never** on the
  default/verified leaderboard.
- A `trusted-local` backend run is **never** verified/leaderboard-eligible
  regardless of completion.
- Hard **run deadline** (monotonic) threaded through reviewer → patch → tests →
  oracles → validators; each stage receives `min(stage_timeout, remaining)`.

### 4.5 Execution - Docker-standard

```
docker run --rm
  --network none
  --user <non-root uid:gid>
  --cap-drop ALL
  --security-opt no-new-privileges
  --pids-limit <N> --memory <M> --cpus <C>
  --read-only
  --tmpfs /tmp:rw,noexec,nosuid,size=<S>
  --mount type=bind,src=<solution>,dst=/workspace            # writable
  --mount type=bind,src=<hidden-tests>,dst=/arena/tests,ro   # read-only
  --mount type=bind,src=<oracles>,dst=/arena/oracles,ro      # read-only
  <image@sha256:...>  <argv>
```

- Image resolved to a **digest** before execution; requested ref + resolved
  digest recorded in the manifest.
- Architecture is **not** hard-coded to Python; image is pack-level or
  case-level. An official digest-pinned Python image is provided for current
  packs.
- **No silent fallback.** If Docker is required and unavailable, the case/run is
  `invalid` with a clear reason. `trusted-local` is opt-in only.
- **Full cleanup** on timeout/cancel/interrupt/failure: POSIX `start_new_session`
  + `os.killpg` for local; `docker stop`/`rm` by container id for Docker; covers
  the whole process tree (background `sleep`, nested shells, grandchildren).
- Output (stdout/stderr) byte-capped.

### 4.6 Tamper resistance

- Reject unsafe paths, symlinks, special files (sockets/devices/FIFOs), path
  collisions (case/Unicode), and traversal in **packs** and **patches**.
- Record three path sets: `declared_patch_paths`, `post_apply_changed_paths`,
  `post_execution_changed_paths`.
- Hash hidden tests + oracles **before and after** execution; mismatch ⇒ fail.
- Fail on: forbidden changes, zero-test collection (unless explicitly allowed),
  failure suppression, plugin/config injection
  (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, sanitized `PYTHONPATH`), workspace
  shadowing of the runner.
- Local mode uses an isolated temporary `HOME` and `TMPDIR`; docs state plainly
  it is **containment, not security isolation**.

### 4.7 Pack quality and `certify-pack`

`arena certify-pack <pack>` checks: schema validity; unsafe files/paths; buggy
baseline fails; reference repair passes; required tests actually collect and run;
deterministic across repeated runs; hidden-test integrity; vocabulary
leakage (existing contamination lint); incorrect mutants rejected; alternate
valid repair accepted where practical; validators measure behavior/requirements,
not reference similarity; image digest reproducible; adversarial controls cannot
game the case.

States: `draft → development → certified → verified`. Only **verified** packs +
**docker** complete runs enter the verified leaderboard.

### 4.8 Reproducibility

Content-addressed evidence bundle per run:

```
run.json  manifest.json  environment.json
reviewer-requests.jsonl  reviewer-responses.jsonl
patches/  test-results/  oracle-results/  integrity-results/
report.md  report.html  checksums.json
```

Bundle hash = `sha256(canonical checksums.json)`. `arena verify-run <path>`
detects missing/edited/mismatched artifacts. Provenance recorded: arena version +
build commit (full SHA) + dirty flag + distribution hash; pack checksum; image
digest; reviewer identity + interface version; prompt version; budgets; latency;
cost provenance (`provider_reported` | `arena_calculated` | `unknown`); platform;
architecture; coverage.

### 4.9 CLI and dashboard

CLI surface: `doctor · reviewers · packs · validate · certify-pack · run ·
compare · report · leaderboard · verify-run · serve`. Behaviors: helpful errors,
progress, deterministic case ordering, JSON mode, non-zero exit on
invalid/incomplete runs, CI mode.

Dashboard surfaces: overview · run detail · **case evidence** (input diff,
findings, matched bugs, proposed patch, changed-file sets, test + oracle +
mutation results, final evidence status) · reviewer comparison · packs +
certification · red-team results · run verification · methodology + limitations +
local setup.

---

## 5. Data model and schema diffs (concrete)

`arena/core/models.py`:
- `GroundTruthBug`: add `id: str` (required; default migration `bug-1`).
- New `Oracle` model (§4.2).
- `ExecutionConfig`: rename intent of `docker_image` → keep field, add
  `oracles: list[Oracle]`, `image_digest: str | None` (resolved), `maturity:
  Literal["static_only","executable"]` proxy via `run_tests`/oracles presence.
- `ReviewResult`: add `proposed_patch: str | None`.
- `Finding`: add `id: str`.
- `ScoredFinding`: add `evidence_status: str`.
- `CaseResult`: add `case_status: str`, `bug_repairs: list[BugRepair]`,
  `declared_patch_paths`, `post_apply_changed_paths`,
  `post_execution_changed_paths`, integrity result.
- New per-run scoring models: `ReviewAccuracy`, `RepairSuccess`,
  `ReviewTrustworthiness`, `RepairConfidenceSummary`. Remove `validated_f_beta`
  from the primary surface (retain legacy column read-only).
- `RunResult`/`RunMetadata`: §4.4 + §4.8 fields.

`arena/storage/`: bump `SCHEMA_VERSION = 2`; add `_migrate_v2` that ALTERs
`runs` (run_status, schema_version, execution_backend, image_digest, coverage
columns, new dimension columns) and `case_results` (case_status, path-set JSON,
integrity); set `run_status = 'legacy'` for all rows present at migration time;
**no back-fill** of new metrics. `findings` gains `evidence_status`.

## 6. Migration plan

- **DB:** additive ALTERs only; legacy rows flagged, never recomputed. New code
  reads legacy rows defensively (nullable new columns).
- **Cases:** a migration script converts `primary_bug → bugs[{id: bug-1}]`, adds
  oracle stubs where `run_tests` is true (single-bug ⇒ one oracle → bug-1), and
  marks `run_tests: false` cases `static_only` / **development-only** (excluded
  from execution-backed claims and verified leaderboard). The legacy
  `primary_bug` accessor (`models.py:71-74`) stays for dashboards.
- **Reviewers:** `command`/`http` reviewers emitting only finding patches still
  work via the single-finding adoption rule (§4.1). Built-in controls + reference
  reviewer updated to emit `proposed_patch`.

## 7. Affected-file map

- Contract/scoring: `core/models.py`, `reviewers/{response_parser,base,controls,
  reference_patch,custom_command}.py`, new `reviewers/http.py`,
  `scoring/{scorer,deterministic_scorer,metrics,severity_matcher}.py`, new
  `scoring/evidence.py`.
- Execution/integrity: `execution/{test_executor,sandbox,hardening,commands}.py`,
  new `execution/{docker_backend,process.py,integrity.py}`, `patching/
  patch_applier.py`, `patching/patch_parser.py`.
- Run/lifecycle: `benchmark/benchmark_runner.py`, `benchmark/case_loader.py`,
  new oracle runner; `storage/{db,schema.sql,repository}.py`.
- Reproducibility: new `reports/bundle.py`, `cli/commands/verify_run.py`.
- Packs: new `benchmark/certify.py`, `cli/commands/certify_pack.py`;
  `benchmark_sets/*`.
- Product: `cli/main.py` (+ command modules), `reviewers/redteam/*` (controls),
  `dashboard/*`.

## 8. Phase plan and acceptance tests

Each phase ends green: full pytest, ruff, mypy, dashboard build, plus the listed
acceptance tests. Docker-dependent gates require a running daemon.

1. **Contract + scoring + run validity** (Docker-independent)
   - AT: two-bug case with one combined patch passes; two patches w/o
     `proposed_patch` ⇒ `ambiguous_patch_source`; metric units asserted; partial
     run ⇒ `run_status=partial` and excluded from leaderboard; legacy run loads.
2. **Execution + integrity** (needs Docker)
   - AT: background `sleep`/nested/grandchild all dead after timeout; hardened
     flags asserted in argv; Docker-absent ⇒ `invalid`, no fallback; tampering
     with a mounted test ⇒ fail; tests run from read-only mount.
3. **Evidence attribution**
   - AT: each finding gets the correct `evidence_status`; `detected_but_unrepaired`
     vs `repair_validated` distinguished; `irrelevant_repair` detected.
4. **Reviewer red-team suite** - AT: each control yields its intended failure.
5. **Pack certification** - AT: `certify-pack` rejects a leaking/non-deterministic
   /non-failing-baseline case; mutant-kill measured.
6. **Reproducibility** - AT: `verify-run` detects an edited artifact.
7. **CLI + dashboard** - AT: smoke each command; evidence view renders.
8. **Release** - AT: fresh-clone offline demo green end-to-end.

## 9. Constraints and honest limitations

- **Docker is not running in the current dev environment.** Phase 2+ code can be
  written but its acceptance gates cannot be proven here until the daemon is up.
  This is recorded, not glossed.
- v2 is a **multi-session** effort. "Finished v2" is declared only when official
  packs actually execute, Docker behavior is verified, the dashboard has the
  evidence view, and the fresh-clone offline demo is green - per §8.8.
- Static-only cases remain useful for detection but are excluded from
  execution-backed claims until they ship real oracles.
