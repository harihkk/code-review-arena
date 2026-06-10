"""Storage migrations, run manifests, determinism, and project-root resolution."""

import json
import sqlite3
from pathlib import Path

import pytest

from arena.benchmark.benchmark_runner import run_benchmark
from arena.core.config import project_root, resolve_benchmark_path
from arena.core.errors import StorageError
from arena.reviewers.custom_command import redact_secrets
from arena.reviewers.mock import MockReviewer
from arena.storage.db import SCHEMA_VERSION, connect

REPO_ROOT = Path(__file__).resolve().parent.parent
V1 = REPO_ROOT / "benchmark_sets" / "v1"


def test_connect_enables_wal_and_stamps_schema_version(tmp_path):
    db_path = tmp_path / "arena.db"
    with connect(db_path) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    # Second connect takes the fast path and keeps the stamp.
    with connect(db_path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_connect_refuses_newer_schema(tmp_path):
    db_path = tmp_path / "future.db"
    raw = sqlite3.connect(db_path)
    raw.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    raw.commit()
    raw.close()
    with pytest.raises(StorageError, match="newer"):
        connect(db_path)


def test_legacy_unversioned_database_is_migrated(tmp_path):
    db_path = tmp_path / "legacy.db"
    raw = sqlite3.connect(db_path)
    raw.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, run_json TEXT NOT NULL)")
    raw.commit()
    raw.close()
    with connect(db_path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(runs)").fetchall()}
        assert "validated_f_beta" in columns
        assert db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def _score_fingerprint(run) -> list[tuple]:
    return [
        (case.case_id, case.score, json.dumps(case.breakdown.model_dump(), sort_keys=True))
        for case in run.case_results
    ]


def test_identical_inputs_produce_identical_deterministic_scores(tmp_path):
    first = run_benchmark(V1, MockReviewer("bad"), output_dir=tmp_path / "a", persist=False)
    second = run_benchmark(V1, MockReviewer("bad"), output_dir=tmp_path / "b", persist=False)
    assert _score_fingerprint(first) == _score_fingerprint(second)
    assert first.total_score == second.total_score
    assert first.metadata.pack_checksum == second.metadata.pack_checksum


def test_run_manifest_records_provenance_without_secrets(tmp_path):
    run = run_benchmark(V1, MockReviewer("perfect"), output_dir=tmp_path / "runs", persist=False)
    manifest_path = tmp_path / "runs" / run.run_id / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == run.run_id
    assert manifest["pack_checksum"] == run.metadata.pack_checksum
    assert manifest["reviewer"]["identifier"] == "mock:perfect"
    assert manifest["reviewer"]["config"] == {"mode": "perfect"}
    assert manifest["harness_version"]
    assert len(manifest["cases"]) == run.case_count
    assert {case["case_id"] for case in manifest["cases"]} == {
        case.case_id for case in run.case_results
    }


def test_redact_secrets_masks_credentials():
    template = "review-cli --api-key=sk-12345 --token: abc --header 'Authorization: Bearer xyz' run"
    redacted = redact_secrets(template)
    assert "sk-12345" not in redacted
    assert "xyz" not in redacted
    assert "review-cli" in redacted


def test_project_root_found_from_subdirectory(monkeypatch):
    monkeypatch.delenv("ARENA_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(REPO_ROOT / "tests")
    assert project_root() == REPO_ROOT
    resolved = resolve_benchmark_path(Path("benchmark_sets/v1"))
    assert resolved == REPO_ROOT / "benchmark_sets" / "v1"


def test_project_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_PROJECT_ROOT", str(tmp_path))
    assert project_root() == tmp_path.resolve()
