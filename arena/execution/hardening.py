"""Reduced-privilege environment and resource limits for fixture commands.

Benchmark fixtures are untrusted: packs can come from third parties, and the
test commands they declare run on the host (when local execution is allowed).
Two mitigations apply to every locally executed fixture command:

- the child environment is built from an allowlist instead of inheriting the
  parent environment, so shell secrets and API keys are never exposed;
- POSIX resource limits bound CPU time, file size, open files, and process
  count so a runaway or malicious fixture cannot exhaust the host.

Neither replaces real isolation (containers); they raise the bar for the
default subprocess executor.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

# Variables forwarded from the parent environment when present. Everything
# else requires an explicit opt-in via ARENA_PASSTHROUGH_ENV.
SAFE_ENV_KEYS = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
)


def sandbox_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Minimal allowlisted environment for fixture subprocesses.

    ``ARENA_PASSTHROUGH_ENV`` may name a comma-separated list of additional
    variables to forward explicitly (e.g. a proxy setting a pack's fixtures
    legitimately need). The parent environment is never forwarded wholesale.
    """
    env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    passthrough = os.getenv("ARENA_PASSTHROUGH_ENV", "")
    for name in filter(None, (item.strip() for item in passthrough.split(","))):
        if name in os.environ:
            env[name] = os.environ[name]
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env


def _clamped(limit: int, desired: int) -> tuple[int, int]:
    import resource

    _soft, hard = resource.getrlimit(limit)
    cap = desired if hard == resource.RLIM_INFINITY else min(desired, hard)
    return (cap, cap)


def resource_limiter(cpu_seconds: int) -> Callable[[], None] | None:
    """Return a preexec_fn applying rlimits to the child, or None off-POSIX.

    Limits are env-overridable: ARENA_RLIMIT_AS_BYTES, ARENA_RLIMIT_FSIZE_BYTES,
    ARENA_RLIMIT_NOFILE, ARENA_RLIMIT_NPROC. The CPU ceiling follows the
    command's wall-clock timeout. Children inherit the limits, so forked
    helpers stay bounded too.
    """
    if sys.platform == "win32":
        return None
    address_space = int(os.getenv("ARENA_RLIMIT_AS_BYTES", str(4 * 1024**3)))
    file_size = int(os.getenv("ARENA_RLIMIT_FSIZE_BYTES", str(256 * 1024**2)))
    open_files = int(os.getenv("ARENA_RLIMIT_NOFILE", "512"))
    processes = int(os.getenv("ARENA_RLIMIT_NPROC", "2048"))

    def set_limits() -> None:
        import resource

        resource.setrlimit(
            resource.RLIMIT_CPU, _clamped(resource.RLIMIT_CPU, max(cpu_seconds, 1) + 5)
        )
        resource.setrlimit(resource.RLIMIT_FSIZE, _clamped(resource.RLIMIT_FSIZE, file_size))
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, _clamped(resource.RLIMIT_NOFILE, open_files))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, _clamped(resource.RLIMIT_NPROC, processes))
        except (ValueError, OSError):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_AS, _clamped(resource.RLIMIT_AS, address_space))
        except (ValueError, OSError):
            # macOS rejects RLIMIT_AS in some configurations; the other limits
            # still apply.
            pass

    return set_limits
