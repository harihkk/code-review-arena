"""Reviewer output contract: schema export, verify-reviewer, repair path."""

import json
from pathlib import Path

from typer.testing import CliRunner

from arena.benchmark.case_loader import build_context, load_cases
from arena.cli.main import app
from arena.reviewers.custom_command import CustomCommandReviewer
from arena.reviewers.response_parser import naive_repair, parse_review_response

runner = CliRunner()
FIXTURES = Path("tests/fixtures/fake_reviewers")


def test_schema_command_emits_versioned_review_schema():
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema["version"]
    assert "findings" in schema["properties"]
    assert "overall_risk" in schema["properties"]
    # The case-level repair is part of the contract but optional, so it never
    # widens the required set (legacy reviewers stay valid).
    assert "proposed_patch" in schema["properties"]
    assert set(schema["required"]) == {"findings", "overall_risk", "review_summary"}


def test_naive_repair_wraps_bare_list_and_drops_invalid_findings():
    valid_finding = {
        "title": "t",
        "summary": "s",
        "category": "correctness",
        "severity": "low",
        "file": "a.py",
        "line_start": 1,
        "line_end": 1,
        "evidence": "e",
        "confidence": 0.5,
    }
    raw = json.dumps([valid_finding, {"title": "broken"}])
    parsed, attempts = parse_review_response(raw, repair=naive_repair)
    assert parsed is not None
    assert attempts == 3
    assert len(parsed.findings) == 1
    assert parsed.overall_risk == "medium"
    # Without repair the same payload is rejected.
    rejected, _ = parse_review_response(raw)
    assert rejected is None


def test_repair_is_opt_in_for_custom_command():
    case = load_cases(Path("benchmark_sets/audit_v1"))[0]
    context = build_context(case)
    command = f"python {FIXTURES / 'bare_list_reviewer.py'} {{case_json}}"
    strict = CustomCommandReviewer(command, timeout_seconds=30).review(context)
    assert strict.invalid_output is True
    repaired = CustomCommandReviewer(command, timeout_seconds=30, enable_repair=True).review(
        context
    )
    assert repaired.invalid_output is False
    assert repaired.parse_attempts == 3
    assert repaired.parsed_response is not None
    assert len(repaired.parsed_response.findings) == 1


def test_control_spec_and_deprecated_mock_alias(capsys):
    from arena.core.registry import create_reviewer
    from arena.reviewers.controls import ControlReviewer

    control = create_reviewer("control:keyword_gamer")
    assert isinstance(control, ControlReviewer)
    assert control.identifier == "control:keyword_gamer"
    legacy = create_reviewer("mock:keyword_gamer")
    assert isinstance(legacy, ControlReviewer)
    assert legacy.identifier == "control:keyword_gamer"
    assert "DEPRECATED" in capsys.readouterr().err
    assert create_reviewer("control:reference_patch").name == "reference-patch"


def test_verify_reviewer_accepts_valid_wrapper():
    result = runner.invoke(
        app,
        [
            "verify-reviewer",
            "benchmark_sets/audit_v1",
            "--command",
            f"python {FIXTURES / 'valid_reviewer.py'} {{case_json}}",
        ],
    )
    assert result.exit_code == 0
    assert "VALID" in result.stdout


def test_verify_reviewer_explains_contract_violations():
    result = runner.invoke(
        app,
        [
            "verify-reviewer",
            "benchmark_sets/audit_v1",
            "--command",
            f"python {FIXTURES / 'invalid_json_reviewer.py'} {{case_json}}",
        ],
    )
    assert result.exit_code == 1
    assert "INVALID" in result.stdout
