"""Parsing and normalization for fixture test commands.

Fixture commands always run without a shell. A case may declare
``test_command`` as a single command string, one argv list, or a list of argv
lists (each executed in order, all must pass). Shell operators have no meaning
without a shell, so commands relying on them are rejected up front — at
``arena validate`` time rather than mid-run.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import PurePosixPath

from arena.core.errors import ValidationError

_SHELL_OPERATORS = {"&&", "||", ";", "|", ">", ">>", "<", "<<", "&"}


def pin_interpreter(argv: list[str]) -> list[str]:
    """Pin python/pytest invocations to the harness interpreter.

    Only valid for local execution; inside a container the image's own
    interpreter must be used, so docker commands stay untouched.
    """
    program = PurePosixPath(argv[0]).name
    if program == "pytest":
        return [sys.executable, "-m", "pytest", *argv[1:]]
    if program in {"python", "python3"}:
        return [sys.executable, *argv[1:]]
    return argv


def _validate_argv(argv: list[str], original: object) -> list[str]:
    if not argv:
        raise ValidationError(f"test_command contains an empty command: {original!r}")
    for token in argv:
        if not isinstance(token, str):
            raise ValidationError(f"test_command tokens must be strings: {original!r}")
        if token in _SHELL_OPERATORS:
            raise ValidationError(
                f"test_command uses shell operator {token!r}; commands run without a "
                f"shell — declare a list of argv commands instead: {original!r}"
            )
    head = argv[0]
    if any(operator in head for operator in (";", "|", "&")):
        raise ValidationError(f"test_command program name looks like a shell snippet: {head!r}")
    return argv


def parse_test_commands(value: str | list | None) -> list[list[str]]:
    """Normalize a case test_command into an ordered list of argv commands."""
    if value is None:
        return []
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            argv = shlex.split(value)
        except ValueError as exc:
            raise ValidationError(f"test_command is not parseable: {value!r} ({exc})") from exc
        return [_validate_argv(argv, value)]
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return [_validate_argv(list(value), value)] if value else []
        if all(isinstance(item, list) for item in value):
            return [_validate_argv(list(item), item) for item in value]
        raise ValidationError(
            f"test_command list must be one argv list or a list of argv lists: {value!r}"
        )
    raise ValidationError(f"test_command has unsupported type {type(value).__name__}")
