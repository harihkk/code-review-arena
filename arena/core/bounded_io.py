"""Bounded readers for externally controlled input (pack files, diffs, patches).

Pydantic field limits run AFTER YAML/JSON has been parsed, so they do not bound
the raw document. These readers enforce a byte ceiling BEFORE decoding or
parsing: they lstat and reject symlinks and non-regular files, open with
``O_NOFOLLOW`` where available, read at most ``limit + 1`` bytes, reject (never
truncate) when oversized, and only then decode UTF-8 strictly. The missing,
unsafe-type, too-large, invalid-UTF-8, and malformed cases are distinguishable
via typed exceptions, and an error never includes the file's contents.

This bounds memory and parser amplification. It does NOT address source
mutability or time-of-check/time-of-use between reading and later execution;
immutable pack snapshots remain Phase 1C.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import yaml
from yaml.events import AliasEvent
from yaml.nodes import Node

from arena.core.errors import (
    InputTooLargeError,
    InvalidEncodingError,
    UnsafeInputError,
    ValidationError,
)

_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def _read_at_most(path: Path, count: int, *, label: str) -> bytes:
    """Read up to ``count`` bytes from a regular file, rejecting unsafe types.

    A leading lstat rejects symlinks and special files with a clear message;
    O_NOFOLLOW guards the open against a symlink raced in afterward. This neither
    rejects nor truncates on size; callers decide what an over-limit read means.
    """
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ValidationError(f"missing {label}: {path}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise UnsafeInputError(f"{label} is a symlink and will not be read: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise UnsafeInputError(f"{label} is not a regular file: {path}")
    try:
        descriptor = os.open(path, _OPEN_FLAGS)
    except OSError as exc:
        raise UnsafeInputError(f"{label} could not be opened safely: {path}") from exc
    try:
        with os.fdopen(descriptor, "rb") as handle:
            return handle.read(count)
    except OSError as exc:
        raise UnsafeInputError(f"{label} could not be read: {path}") from exc


def read_bytes_bounded(path: Path, limit: int, *, label: str) -> bytes:
    """Read at most ``limit`` bytes from a regular file, or raise a typed error.

    Reads ``limit + 1`` bytes and treats the actual count as authoritative, so a
    file is rejected (not truncated) when it exceeds the limit.
    """
    data = _read_at_most(path, limit + 1, label=label)
    if len(data) > limit:
        raise InputTooLargeError(f"{label} exceeds the {limit}-byte limit: {path}")
    return data


def read_text_bounded(path: Path, limit: int, *, label: str) -> str:
    """Bounded read plus strict UTF-8 decode (after the byte check)."""
    data = read_bytes_bounded(path, limit, label=label)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidEncodingError(f"{label} is not valid UTF-8: {path}") from exc


def read_text_capped(path: Path, limit: int, *, label: str) -> tuple[str, bool]:
    """Reviewer-context read: return at most ``limit`` decoded bytes plus a truncated flag.

    Unlike :func:`read_text_bounded`, this TRUNCATES rather than rejecting, because
    reviewer source context records truncation as an explicit part of its contract,
    and decodes leniently so a non-UTF-8 source file is still surfaced. It still
    rejects symlinks and special files, and never reads more than ``limit + 1`` bytes.
    """
    data = _read_at_most(path, limit + 1, label=label)
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


class _NoAliasSafeLoader(yaml.SafeLoader):
    """SafeLoader that refuses YAML aliases (the billion-laughs amplification vector)."""


def _forbid_alias(loader: yaml.SafeLoader, parent: Node | None, index: int) -> Node | None:
    if loader.check_event(AliasEvent):
        raise ValidationError("YAML aliases are not allowed in pack files")
    return yaml.SafeLoader.compose_node(loader, parent, index)


_NoAliasSafeLoader.compose_node = _forbid_alias  # type: ignore[assignment]


def read_yaml_mapping_bounded(path: Path, limit: int, *, label: str) -> dict:
    """Bounded read, then parse YAML with aliases forbidden and a mapping root required."""
    text = read_text_bounded(path, limit, label=label)
    try:
        data = yaml.load(text, Loader=_NoAliasSafeLoader)
    except yaml.YAMLError as exc:
        raise ValidationError(f"{label} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{label} must be a YAML mapping at the document root: {path}")
    return data
