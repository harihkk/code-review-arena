# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue.
Use GitHub's private vulnerability reporting: open the repository's **Security**
tab and choose **Report a vulnerability**. Include steps to reproduce, the
affected version or commit, and the impact you observed. You can expect an
initial response within a few days.

Please do not file public issues, pull requests, or discussion posts for
undisclosed vulnerabilities until a fix is available.

## Scope and threat model

CodeReview Arena runs untrusted input by design: reviewer outputs, candidate
patches, and benchmark packs may all be adversarial. The harness is built around
that assumption, and reports about the following are in scope:

- A candidate patch escaping the workspace, reaching the network, or tampering
  with the hidden tests or oracle during a run.
- A benchmark pack reading or writing outside its own tree when loaded or
  executed (for example through symlinks, special files, or path traversal).
- The sandbox boundary being bypassed in the Docker backend (network, dropped
  capabilities, read-only root, non-root user, resource limits, no implicit
  image pulls).
- Ground-truth answers leaking into the reviewer-visible payload.

The local API server is explicitly **not hardened for public exposure**. It is
meant to run on a trusted machine; exposing it to untrusted callers is outside
the supported configuration. Local test execution is opt-in
(`--allow-local-execution`, or `ARENA_SERVER_ALLOW_LOCAL_EXECUTION` for the API)
because it runs fixture-owned commands on the host; prefer the Docker backend for
untrusted packs.

For defense in depth, set `ARENA_TRUSTED_PACK_HASHES` (a space- or comma-separated
list of pack `sha256` values, as printed by `arena pack-hash`) to restrict local
execution to specific trusted packs. When it is set, a pack whose checksum is not
listed will not run on the host even if `--allow-local-execution` is passed, so a
single opt-in no longer trusts every pack.

## Supported versions

The project has not cut a tagged release yet. Until it does, only the latest
`main` is supported.
