"""Execution security: env allowlist, resource limits, pack checksums, path validation."""

import sys
from pathlib import Path

from arena.benchmark.pack_hash import pack_checksum, stored_checksum, write_checksum
from arena.core.config import resolve_benchmark_set
from arena.execution.hardening import sandbox_env
from arena.execution.test_executor import TestExecutionRequest, TestExecutor


def test_sandbox_env_does_not_inherit_parent_environment(monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_API_KEY", "leak-me")
    env = sandbox_env()
    assert "SUPER_SECRET_API_KEY" not in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "PATH" in env


def test_sandbox_env_passthrough_is_explicit(monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_API_KEY", "leak-me")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    monkeypatch.setenv("ARENA_PASSTHROUGH_ENV", "HTTPS_PROXY")
    env = sandbox_env()
    assert env["HTTPS_PROXY"] == "http://proxy:3128"
    assert "SUPER_SECRET_API_KEY" not in env


def test_fixture_commands_cannot_read_host_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_API_KEY", "leak-me")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = TestExecutor().execute(
        TestExecutionRequest(
            case_id="case",
            workspace_path=workspace,
            test_command=[
                sys.executable,
                "-c",
                "import os; print(os.environ.get('SUPER_SECRET_API_KEY', 'BLOCKED'))",
            ],
            timeout_seconds=10,
            allow_local_execution=True,
        )
    )
    assert result.ran is True
    assert "BLOCKED" in result.stdout
    assert "leak-me" not in result.stdout


def test_file_size_rlimit_stops_disk_filling(tmp_path, monkeypatch):
    if sys.platform == "win32":
        return
    monkeypatch.setenv("ARENA_RLIMIT_FSIZE_BYTES", str(64 * 1024))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = TestExecutor().execute(
        TestExecutionRequest(
            case_id="case",
            workspace_path=workspace,
            test_command=[
                sys.executable,
                "-c",
                "open('big.bin','wb').write(b'x' * (1024 * 1024)); print('WROTE')",
            ],
            timeout_seconds=10,
            allow_local_execution=True,
        )
    )
    assert result.ran is True
    assert result.passed is False
    assert "WROTE" not in result.stdout


def _make_pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pack"
    (pack / "case_a").mkdir(parents=True)
    (pack / "manifest.yaml").write_text("version: x\nname: x\ncases: [case_a]\n", "utf-8")
    (pack / "case_a" / "case.yaml").write_text("id: case_a\n", "utf-8")
    return pack


def test_pack_checksum_pins_content(tmp_path):
    pack = _make_pack(tmp_path)
    first = pack_checksum(pack)
    assert first == pack_checksum(pack)
    (pack / "case_a" / "case.yaml").write_text("id: case_a_tampered\n", "utf-8")
    assert pack_checksum(pack) != first


def test_pack_checksum_ignores_hidden_files_and_itself(tmp_path):
    pack = _make_pack(tmp_path)
    baseline = pack_checksum(pack)
    checksum = write_checksum(pack)
    (pack / ".DS_Store").write_bytes(b"junk")
    assert pack_checksum(pack) == baseline == checksum
    assert stored_checksum(pack) == checksum


def test_resolve_benchmark_set_rejects_path_tricks(monkeypatch, tmp_path):
    root = tmp_path / "packs"
    (root / "v1").mkdir(parents=True)
    monkeypatch.setenv("ARENA_BENCHMARK_ROOT", str(root))
    assert resolve_benchmark_set("v1") == root / "v1"
    assert resolve_benchmark_set("../packs/v1") is None
    assert resolve_benchmark_set("a/b") is None
    assert resolve_benchmark_set("..") is None
    assert resolve_benchmark_set("") is None
    assert resolve_benchmark_set("missing") is None
