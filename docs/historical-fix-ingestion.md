# Historical-fix ingestion (`arena import-fix`)

`arena import-fix` turns a known buggy/fixed commit pair in a **local** Git
repository into a candidate Code Review Arena pack. It is the first
post-architecture product feature and is deliberately conservative:
local-only, offline, provider-neutral, deterministic, non-AI, non-publishing, and
non-executing during import.

```bash
arena import-fix \
  --repo /path/to/local/repository \
  --buggy-commit <full-object-id> \
  --fixed-commit <full-object-id> \
  --spec import-spec.yaml \
  --output /path/to/candidate-pack \
  --source-label owner/repository      # optional, persisted; never a local path
```

## Why the generated case is synthetic

The importer builds a **reverse-fix review case**. Given a buggy commit `B` and a
fixed commit `F` (with `B` an ancestor of `F`) it generates:

```
after/           selected source content at B   (the buggy state under review)
before/          selected source content at F   (the fixed state)
reference.patch  exact repair diff  B -> F       (after/ + reference.patch == F)
pr.diff          inverse review diff F -> B       (before/ + pr.diff == after/)
tests/           selected test content at F
```

This matches the Arena convention `before -> pr.diff -> after (buggy)` and
`after/ + reference.patch -> fixed solution`. It is a **synthetic** review case
derived from a real historical fix; it is **not** the original bug-introducing
pull request, and its `pr.diff` is the reverse of the real change. Treat the
synthetic review as a plausible "what if this fix were proposed in reverse"
exercise, not as the literal history.

## Required human specification

The importer never infers semantics. A strict `import-spec.yaml` supplies
everything that cannot be derived safely (title, category, severity, description,
ground truth, execution/validation config, and which committed paths are source
vs tests). It reuses the normal case models, so a spec that would not make a valid
`BenchmarkCase` is rejected. See the command help and `arena/importer/import_spec.py`
for the exact shape; unknown fields fail.

## Local, offline threat model

The source repository's mutable working tree is **ignored completely**: the
importer reads committed objects only (`git ls-tree`, `git cat-file`, and `git
diff` between two commits), reusing the Phase 1D isolated Git environment (private
empty HOME/config, no system/global config, no hooks, no pager/editor/credentials,
no network, fixed locale, bounded incremental output, timeout and process-group
cleanup). It never runs `checkout`, `clone`, `fetch`, build scripts, or repository
code. Commit ids must be full object ids (40 hex for SHA-1, 64 for SHA-256);
abbreviated ids, branch names, tags, and non-commit objects are rejected, as are
unrelated histories and a fixed commit that is not descended from the buggy commit.

## Changed-path classification

Every path changed between `B` and `F` must be classified as either selected
**source** (copied into `before/` and `after/`, and diffed into `reference.patch`/
`pr.diff`) or selected **tests** (copied from `F` into `tests/`, and excluded from
the diffs because benchmark tests are protected evidence, not reviewer-editable
content). A changed path outside both selections, or an overlap between source and
tests, fails loudly -- the importer never silently omits a historical change.
Symlinks, gitlinks/submodules, special modes, binary changes, unsafe or colliding
paths, and oversized inputs are rejected.

## Deterministic provenance

The same repository objects and spec produce **byte-identical** output and the
same `pack.sha256` on every run. Each case carries a strict `provenance.json`
recording the mode (`reverse_fix`), optional source label, Git object format, the
full buggy/fixed/merge-base ids, the selected source paths and tests root, the
classified changed paths, and the SHA-256 of both generated diffs. It deliberately
omits generation time, username, hostname, and any absolute repository/output/temp
path. Output is staged and atomically renamed, so a failed import leaves no partial
pack, and the importer refuses to overwrite an existing output directory.

## Import does not certify

Import runs strict validation and a contamination scan, and proves both generated
diffs reproduce their target trees through the Phase 1D Git-authoritative pipeline,
but it does **not** run tests, structural validators, mutation testing, or
certification, and it does not add the case to the shipped `benchmark_sets`. The
import report ends with `certification: not run`. After reviewing the candidate
manually, certify it as a separate, explicit step (Docker by default):

```bash
arena validate <candidate-pack>
arena lint-cases <candidate-pack> --strict
arena certify-pack <candidate-pack>
```

## Limitations of this first version

- Local repositories only; no hosted GitHub/GitLab ingestion or network access.
- Binary source changes are rejected; only UTF-8 text diffs are supported.
- Each invocation imports exactly one case from one commit pair.
- A fix that changes a Phase 1D protected file (for example `pyproject.toml` or a
  `conftest.py`) cannot be reproduced as a reviewer-editable repair and is rejected.
- An imported case is a **candidate only**. It is not production-ready, certified,
  or research-valid until it passes the certification ladder and human review.
