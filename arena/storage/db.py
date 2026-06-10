"""SQLite connection lifecycle with versioned, idempotent migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from arena.core.errors import StorageError

SCHEMA_VERSION = 1


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    _migrate(connection)
    return connection


def _migrate_v1(connection: sqlite3.Connection) -> None:
    """Base schema plus the columns that were added before versioning existed."""
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    connection.executescript(schema)
    _add_columns(
        connection,
        "runs",
        {
            "beta": "REAL",
            "deterministic_precision": "REAL",
            "deterministic_recall": "REAL",
            "deterministic_f1": "REAL",
            "deterministic_f_beta": "REAL",
            "patch_apply_rate": "REAL",
            "test_pass_rate": "REAL",
            "structural_pass_rate": "REAL",
            "false_positives_per_case": "REAL",
            "cost_per_true_positive": "REAL",
            "detection_precision": "REAL",
            "detection_recall": "REAL",
            "detection_f1": "REAL",
            "detection_f_beta": "REAL",
            "validated_precision": "REAL",
            "validated_recall": "REAL",
            "validated_f1": "REAL",
            "validated_f_beta": "REAL",
            "deterministic_pass_rate": "REAL",
            "cost_per_validated_fix": "REAL",
            "latency_per_case_ms": "REAL",
        },
    )
    _add_columns(
        connection,
        "case_results",
        {
            "deterministic_pass": "BOOLEAN",
            "patch_provided": "BOOLEAN",
            "patch_applied": "BOOLEAN",
            "tests_ran": "BOOLEAN",
            "tests_passed": "BOOLEAN",
            "structural_validation_ran": "BOOLEAN",
            "structural_validation_passed": "BOOLEAN",
            "failure_reasons_json": "TEXT",
            "patch_error": "TEXT",
        },
    )


# Ordered migration steps; entry N migrates a version-(N-1) database to N.
_MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_migrate_v1]


def _migrate(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        raise StorageError(
            f"database schema version {version} is newer than this arena understands "
            f"({SCHEMA_VERSION}); upgrade codereview-arena instead of downgrading the database"
        )
    for step in range(version, SCHEMA_VERSION):
        _MIGRATIONS[step](connection)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.commit()


def _add_columns(connection: sqlite3.Connection, table: str, expected: dict[str, str]) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, data_type in expected.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {data_type}")
