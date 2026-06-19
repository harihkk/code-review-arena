import time
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from arena.cli.main import app
from arena.server.main import app as server_app

runner = CliRunner()


def _finished_job(client: TestClient, created_response, timeout: float = 180.0) -> dict:
    assert created_response.status_code == 202
    job_id = created_response.json()["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/runs/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_cli_list_and_validate():
    listed = runner.invoke(app, ["list-cases"])
    assert listed.exit_code == 0
    assert "fastapi_auth_bypass" in listed.stdout
    validated = runner.invoke(app, ["validate", "benchmark_sets/v1"])
    assert validated.exit_code == 0


def test_api_health_and_cases():
    client = TestClient(server_app)
    assert client.get("/health").json()["status"] == "ok"
    cases = client.get("/cases").json()
    assert len(cases) == 10
    detail = client.get("/cases/fastapi_auth_bypass_001").json()
    assert "pr.diff" not in detail["diff"]
    assert "delete_user" in detail["diff"]
    assert detail["ground_truth"]["primary_bug"]["files"][0]["path"] == "app/routes/admin.py"


def test_api_can_browse_audit_pack_reference_patches():
    client = TestClient(server_app)
    cases = client.get("/cases", params={"benchmark_set": "audit_v1"}).json()
    assert len(cases) == 10
    assert all(case["benchmark_set"] == "audit_v1" for case in cases)
    detail = client.get(
        "/cases/security_fastapi_multitenant_admin_bypass_001",
        params={"benchmark_set": "audit_v1"},
    ).json()
    assert detail["reference_patch"]
    assert detail["benchmark_set"] == "audit_v1"


def test_api_can_browse_audit_v2():
    # The second pack must be reachable through the API, not just the CLI.
    client = TestClient(server_app)
    cases = client.get("/cases", params={"benchmark_set": "audit_v2"}).json()
    assert len(cases) == 10
    assert all(case["benchmark_set"] == "audit_v2" for case in cases)
    detail = client.get("/cases/page_count_ceil_001", params={"benchmark_set": "audit_v2"}).json()
    assert detail["reference_patch"]
    assert detail["benchmark_set"] == "audit_v2"


def test_api_run_trace_contains_dashboard_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("ARENA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("ARENA_SERVER_ALLOW_LOCAL_EXECUTION", "1")
    client = TestClient(server_app)
    created = client.post(
        "/runs",
        json={
            "reviewer": "control:false_positive_patch",
            "mode": "full",
            "allow_local_execution": True,
        },
    )
    job = _finished_job(client, created)
    assert job["status"] == "completed"
    run_id = job["run_id"]
    trace = client.get(f"/runs/{run_id}/cases/fastapi_auth_bypass_001").json()
    assert "delete_user" in trace["diff"]
    assert trace["breakdown"]["total"] == 90
    assert trace["ground_truth"]["primary_bug"]["summary"]
    assert trace["patch_applied"] is True
    assert trace["tests_passed"] is True
    assert trace["deterministic_pass"] is False
    # This run executes trusted-local, so it is excluded from the default
    # (verified) leaderboard; opt in to see it.
    leaderboard = client.get("/leaderboard?include_unverified=true").json()
    assert leaderboard[0]["false_positives"] == 10
    assert leaderboard[0]["deterministic_metrics"]["detection_f_beta"] < 1
    assert leaderboard[0]["deterministic_metrics"]["validated_f_beta"] == 0


def test_api_leaderboard_requires_external_digest(monkeypatch, tmp_path):
    # The API /leaderboard goes through RunRepository.leaderboard, so it must apply
    # the same eligibility policy as the file leaderboard: a Docker run whose pack
    # only matched its own (regenerable) pack.sha256 is not externally verified and
    # must not appear on the default leaderboard.
    from datetime import datetime

    from arena.core.config import database_path
    from arena.core.models import RunMetadata, RunResult
    from arena.storage.repository import RunRepository

    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "api.db"))

    def _docker_run(run_id: str, model: str, *, externally_verified: bool) -> RunResult:
        return RunResult(
            run_id=run_id,
            benchmark_set="v1",
            reviewer="control",
            model=model,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            metadata=RunMetadata(
                prompt_version="v2",
                benchmark_version="v1",
                pack_digest_externally_verified=externally_verified,
            ),
            case_results=[],
            total_score=0.0,
            schema_version=2,
            run_status="complete",
            execution_backend="docker",
            mode="full",
            bugs_found=0,
            correct_files=0,
            correct_lines=0,
            false_positives=0,
            total_cost=0.0,
            total_latency_ms=0,
        )

    repo = RunRepository(database_path())
    repo.save(_docker_run("internal", "self-consistent", externally_verified=False))
    repo.save(_docker_run("external", "externally-verified", externally_verified=True))

    client = TestClient(server_app)
    default = {row["model"] for row in client.get("/leaderboard").json()}
    assert default == {"externally-verified"}
    both = {row["model"] for row in client.get("/leaderboard?include_unverified=true").json()}
    assert both == {"self-consistent", "externally-verified"}


def test_api_audit_trace_uses_the_runs_benchmark_pack(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "audit-api.db"))
    monkeypatch.setenv("ARENA_RUNS_DIR", str(tmp_path / "audit-runs"))
    monkeypatch.setenv("ARENA_SERVER_ALLOW_LOCAL_EXECUTION", "1")
    client = TestClient(server_app)
    created = client.post(
        "/runs",
        json={
            # Legacy path form must normalize to the pack name.
            "benchmark_set": "benchmark_sets/audit_v1",
            "reviewer": "reference-patch",
            "mode": "full",
            "allow_local_execution": True,
        },
    )
    job = _finished_job(client, created)
    assert job["status"] == "completed"
    run_id = job["run_id"]
    trace = client.get(f"/runs/{run_id}/cases/security_fastapi_multitenant_admin_bypass_001").json()
    assert "tenant_admin" in trace["diff"]
    assert trace["ground_truth"]["primary_bug"]["summary"]
    assert trace["deterministic_pass"] is True


def test_api_refuses_local_execution_without_server_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "gate.db"))
    monkeypatch.delenv("ARENA_SERVER_ALLOW_LOCAL_EXECUTION", raising=False)
    client = TestClient(server_app)
    refused = client.post(
        "/runs",
        json={"reviewer": "control:perfect", "mode": "full", "allow_local_execution": True},
    )
    assert refused.status_code == 403


def test_api_rejects_unknown_benchmark_set_and_reviewer(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "bad.db"))
    client = TestClient(server_app)
    assert client.post("/runs", json={"benchmark_set": "../etc"}).status_code == 400
    assert client.post("/runs", json={"benchmark_set": "missing_pack"}).status_code == 400
    assert client.post("/runs", json={"reviewer": "nonsense"}).status_code == 400


def test_api_token_required_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("ARENA_RUNS_DIR", str(tmp_path / "auth-runs"))
    monkeypatch.setenv("ARENA_API_TOKEN", "sekrit")
    client = TestClient(server_app)
    denied = client.post("/runs", json={"reviewer": "control:perfect"})
    assert denied.status_code == 401
    accepted = client.post(
        "/runs",
        json={"reviewer": "control:perfect"},
        headers={"X-Arena-Token": "sekrit"},
    )
    job = _finished_job(client, accepted)
    assert job["status"] == "completed"


def test_cli_leaderboard_supports_validated_metric(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    runs_dir = tmp_path / "runs"
    # Pin the runs/db locations like the sibling tests do, so the run writes
    # where the leaderboard reads regardless of how project_root() resolves the
    # working directory during a full-suite run.
    monkeypatch.setenv("ARENA_RUNS_DIR", str(runs_dir))
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "leaderboard.db"))
    source = Path(__file__).parent.parent / "benchmark_sets" / "v1"
    created = runner.invoke(
        app,
        [
            "run",
            str(source),
            "--reviewer",
            "control:perfect_patch",
            "--mode",
            "full",
            "--allow-local-execution",
        ],
    )
    assert created.exit_code == 0
    assert "Detection: detection_f_beta=1.000" in created.stdout
    assert "validated_f_beta=1.000" in created.stdout
    # The run is trusted-local, so include it explicitly (excluded by default).
    ranked = runner.invoke(
        app,
        [
            "leaderboard",
            str(runs_dir),
            "--metric",
            "validated_f_beta",
            "--beta",
            "1.0",
            "--include-unverified",
        ],
    )
    assert ranked.exit_code == 0
    from arena.reports.leaderboard import leaderboard_rows

    rows = leaderboard_rows(runs_dir, metric="validated_f_beta", beta=1.0, include_unverified=True)
    assert rows
    assert rows[0]["model"] == "perfect_patch"
    assert rows[0]["metric_value"] == 1.0
