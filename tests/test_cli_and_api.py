from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from arena.cli.main import app
from arena.server.main import app as server_app

runner = CliRunner()


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


def test_api_run_trace_contains_dashboard_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("ARENA_RUNS_DIR", str(tmp_path / "runs"))
    client = TestClient(server_app)
    created = client.post(
        "/runs",
        json={
            "reviewer": "mock:false_positive_patch",
            "mode": "full",
            "allow_local_execution": True,
        },
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    trace = client.get(f"/runs/{run_id}/cases/fastapi_auth_bypass_001").json()
    assert "delete_user" in trace["diff"]
    assert trace["breakdown"]["total"] == 90
    assert trace["ground_truth"]["primary_bug"]["summary"]
    assert trace["patch_applied"] is True
    assert trace["tests_passed"] is True
    assert trace["deterministic_pass"] is False
    leaderboard = client.get("/leaderboard").json()
    assert leaderboard[0]["false_positives"] == 10
    assert leaderboard[0]["deterministic_metrics"]["detection_f_beta"] < 1
    assert leaderboard[0]["deterministic_metrics"]["validated_f_beta"] == 0


def test_cli_leaderboard_supports_validated_metric(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    runs_dir = tmp_path / "runs"
    source = Path(__file__).parent.parent / "benchmark_sets" / "v1"
    created = runner.invoke(
        app,
        [
            "run",
            str(source),
            "--reviewer",
            "mock:perfect_patch",
            "--mode",
            "full",
            "--allow-local-execution",
        ],
    )
    assert created.exit_code == 0
    assert "Detection: detection_f_beta=1.000" in created.stdout
    assert "validated_f_beta=1.000" in created.stdout
    ranked = runner.invoke(
        app,
        ["leaderboard", str(runs_dir), "--metric", "validated_f_beta", "--beta", "1.0"],
    )
    assert ranked.exit_code == 0
    from arena.reports.leaderboard import leaderboard_rows

    rows = leaderboard_rows(runs_dir, metric="validated_f_beta", beta=1.0)
    assert rows
    assert rows[0]["model"] == "perfect_patch"
    assert rows[0]["metric_value"] == 1.0
