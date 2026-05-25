"""Future Docker-backed execution hook.

Local temporary-directory execution is the deterministic default. This class keeps
the extension boundary explicit for untrusted third-party benchmark fixtures.
"""

from pathlib import Path

from arena.execution.subprocess_runner import CommandResult


class DockerRunner:
    def run(self, root: Path, command: str, timeout_seconds: int) -> CommandResult:
        raise NotImplementedError("Docker execution is reserved for external benchmark packs.")
