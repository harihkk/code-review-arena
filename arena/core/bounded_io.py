"""Bounded readers for externally controlled input (pack files, diffs, patches).

Pydantic field limits run AFTER YAML/JSON has been parsed, so they do not bound
the raw document. These readers enforce a byte ceiling BEFORE decoding or
parsing: they lstat and reject symlinks and non-regular files, open with
``O_NOFOLLOW`` where available, read at most ``limit + 1`` bytes, reject (never
truncate) when oversized, and only then decode UTF-8 strictly. The missing,
unsafe-type, too-large, invalid-UTF-8, and malformed cases are distinguishable
via typed exceptions, and an error never includes the file's contents.

After the byte cap, YAML parsing is additionally bounded: aliases are forbidden,
duplicate mapping keys are rejected, and nesting depth and node count are capped,
so a small document cannot amplify into a large or deeply recursive structure.

This bounds individual input bytes and parsed-YAML structure. It does NOT bound
total filesystem entry count, nor provide immutable traversal, name-collision
handling, or time-of-check/time-of-use protection between reading and later
execution; that comprehensive enforcement remains Phase 1C.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node

from arena.core import limits
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


class _BoundedSafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects aliases, duplicate keys, and excessive structure.

    A byte cap alone does not stop parser amplification: aliases enable
    billion-laughs expansion, and deep nesting or huge node counts can exhaust
    memory or recursion even within the byte limit. This loader caps compose-time
    node count and nesting depth, forbids aliases, and rejects duplicate mapping
    keys at every level. It stays a SafeLoader (no arbitrary object construction).
    """

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._node_count = 0
        self._depth = 0

    def compose_node(self, parent: Node | None, index: int) -> Node | None:
        if self.check_event(AliasEvent):
            raise ValidationError("YAML aliases are not allowed in pack files")
        self._node_count += 1
        if self._node_count > limits.YAML_MAX_NODES:
            raise ValidationError("YAML document has too many nodes")
        self._depth += 1
        if self._depth > limits.YAML_MAX_DEPTH:
            raise ValidationError("YAML document is nested too deeply")
        try:
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict:
        # super() collapses duplicate keys (last wins) and raises on unhashable
        # keys; a smaller result than the raw pair count means a duplicate key.
        mapping = super().construct_mapping(node, deep=deep)
        if len(mapping) != len(node.value):
            raise ValidationError("duplicate key in a YAML mapping")
        return mapping


def read_yaml_mapping_bounded(path: Path, limit: int, *, label: str) -> dict:
    """Bounded read, then parse YAML with aliases, duplicate keys, and excessive
    nesting/node-count rejected, and a mapping document root required.

    The structural rejections raise typed ``ValidationError`` directly. A parser
    error or parser-driven ``RecursionError`` is converted to a typed
    ``ValidationError`` whose message names only the failure, never input content.
    """
    text = read_text_bounded(path, limit, label=label)
    try:
        data = yaml.load(text, Loader=_BoundedSafeLoader)
    except ValidationError:
        raise
    except (yaml.YAMLError, RecursionError) as exc:
        raise ValidationError(f"{label} is not valid YAML ({type(exc).__name__})") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"{label} must be a YAML mapping at the document root: {path}")
    return data
