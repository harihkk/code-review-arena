"""SQLite connection lifecycle."""

import sqlite3
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
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
    return connection


def _add_columns(connection: sqlite3.Connection, table: str, expected: dict[str, str]) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, data_type in expected.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {data_type}")
