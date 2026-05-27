"""Generate dashboard verification evidence from commands actually run and saved control runs."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT = "Code Review Arena"
BASELINES = {
    "reference-patch": "Known-good patch artifacts",
    "mock:perfect_patch": "Harness happy path",
    "mock:keyword_gamer": "Plausible comments fail validation",
    "mock:bad_patch": "Detects but supplies bad fixes",
    "mock:malformed_patch": "Detects but supplies an invalid patch",
}


def checked_at() -> str:
    return datetime.now(UTC).isoformat()


def unknown(command: str, explanation: str) -> dict[str, Any]:
    return {
        "status": "unknown",
        "checked_at": None,
        "command": command,
        "explanation": explanation,
    }


def run_check(command: list[str], cwd: Path, explanation: str) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    return {
        "status": "passing" if completed.returncode == 0 else "failing",
        "checked_at": checked_at(),
        "command": " ".join(command),
        "explanation": explanation,
        "output_tail": (completed.stdout + completed.stderr)[-1000:],
    }


def baseline_key(run: dict[str, Any]) -> str:
    reviewer = str(run.get("reviewer", ""))
    model = str(run.get("model") or "")
    return f"{reviewer}:{model}" if model else reviewer


def read_baselines(runs_dir: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for path in sorted(runs_dir.glob("*/run.json")):
        try:
            run = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if run.get("benchmark_set") != "audit_v1":
            continue
        key = baseline_key(run)
        if key not in BASELINES:
            continue
        if key not in latest or str(run.get("completed_at", "")) > str(latest[key].get("completed_at", "")):
            latest[key] = run

    results: dict[str, dict[str, Any]] = {}
    for key, meaning in BASELINES.items():
        run = latest.get(key)
        if not run:
            results[key] = {
                "status": "unknown",
                "checked_at": None,
                "command": baseline_command(key),
                "meaning": meaning,
                "metrics": None,
                "run_id": None,
            }
            continue
        metrics = run.get("deterministic_metrics") or {}
        case_results = run.get("case_results") or []
        passes = sum(item.get("deterministic_pass") is True for item in case_results)
        status = expected_status(key, metrics, passes, len(case_results))
        results[key] = {
            "status": status,
            "checked_at": run.get("completed_at"),
            "command": baseline_command(key),
            "meaning": meaning,
            "run_id": run.get("run_id"),
            "metrics": {
                "detection_f_beta": metrics.get("detection_f_beta"),
                "validated_f_beta": metrics.get("validated_f_beta"),
                "deterministic_passes": passes,
                "case_count": len(case_results),
            },
        }
    return results


def expected_status(key: str, metrics: dict[str, Any], passes: int, count: int) -> str:
    detection = metrics.get("detection_f_beta")
    validated = metrics.get("validated_f_beta")
    if count == 0:
        return "unknown"
    if key in {"reference-patch", "mock:perfect_patch"}:
        return "passing" if validated == 1.0 and passes == count else "failing"
    if key in {"mock:keyword_gamer", "mock:malformed_patch"}:
        return "passing" if detection == 1.0 and validated == 0.0 and passes == 0 else "failing"
    return "passing" if detection == 1.0 and validated is not None and validated < detection else "failing"


def baseline_command(key: str) -> str:
    return f"arena run benchmark_sets/audit_v1 --reviewer {key} --mode full --allow-local-execution"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dashboard/public/verification.json"))
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--run-validation", action="store_true")
    parser.add_argument("--run-quality-checks", action="store_true")
    parser.add_argument("--run-baselines", action="store_true")
    parser.add_argument("--generate-report", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    validations = {
        "v1": unknown("arena validate benchmark_sets/v1", "Validation has not been run in this snapshot."),
        "audit_v1": unknown("arena validate benchmark_sets/audit_v1", "Validation has not been run in this snapshot."),
    }
    quality = {
        "tests": unknown("make test", "Backend test status is only recorded when executed by the generator."),
        "lint": unknown("make lint", "Lint status is only recorded when executed by the generator."),
        "typecheck": unknown("make typecheck", "Typecheck status is only recorded when executed by the generator."),
        "dashboard_build": unknown("npm run build", "Dashboard build status is only recorded when executed by the generator."),
    }
    capabilities = {
        "audit_report_generation": unknown(
            "arena audit-report runs/ --output docs/reports/audit-v1-results.md",
            "Generate an audit report to capture this status.",
        ),
        "custom_command_reviewer": unknown(
            "pytest tests/test_custom_command_reviewer.py",
            "Run the adapter tests to capture this status.",
        ),
    }

    if args.run_validation:
        validations["v1"] = run_check(["arena", "validate", "benchmark_sets/v1"], root, "Benchmark manifest and fixtures validate.")
        validations["audit_v1"] = run_check(
            ["arena", "validate", "benchmark_sets/audit_v1"], root, "Audit Pack v1 fixtures and validation declarations validate."
        )
    if args.run_baselines:
        for name in BASELINES:
            run_check(
                ["arena", "run", "benchmark_sets/audit_v1", "--reviewer", name, "--mode", "full", "--allow-local-execution"],
                root,
                f"Generated deterministic control run for {name}.",
            )
    if args.run_quality_checks:
        quality["tests"] = run_check(["make", "test"], root, "The Python test suite passed.")
        quality["lint"] = run_check(["make", "lint"], root, "Ruff lint and formatting checks passed.")
        quality["typecheck"] = run_check(["make", "typecheck"], root, "Mypy type checking passed.")
        quality["dashboard_build"] = run_check(["npm", "run", "build"], root / "dashboard", "The Next.js production build completed.")
        quality["dashboard_build"]["command"] = "cd dashboard && npm run build"
        capabilities["custom_command_reviewer"] = run_check(
            ["pytest", "tests/test_custom_command_reviewer.py"], root, "The custom-command adapter tests passed."
        )
    if args.generate_report:
        capabilities["audit_report_generation"] = run_check(
            ["arena", "audit-report", "runs/", "--output", "docs/reports/audit-v1-results.md"],
            root,
            "The dashboard JSON and Markdown audit report were generated from saved runs.",
        )

    snapshot = {
        "project_name": PROJECT,
        "generated_at": checked_at(),
        "benchmark_sets": validations,
        "baselines": read_baselines(root / args.runs_dir),
        "quality_checks": quality,
        "capabilities": capabilities,
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2) + "\n")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
