"""Readable benchmark report rendering."""

from pathlib import Path

from arena.core.models import RunResult


def render_markdown(run: RunResult) -> str:
    lines = [
        "# Code Review Arena Report",
        "",
        f"Benchmark Set: {run.benchmark_set}",
        f"Reviewer: {run.reviewer}{':' + run.model if run.model else ''}",
        f"Run ID: {run.run_id}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Review Quality Score | {run.total_score:.1f} |",
        f"| Bugs Found | {run.bugs_found}/{run.case_count} |",
        f"| Correct File | {run.correct_files}/{run.case_count} |",
        f"| Correct Line | {run.correct_lines}/{run.case_count} |",
        f"| False Positives | {run.false_positives} |",
        f"| Estimated Cost | ${run.total_cost:.4f} |",
        f"| Total Latency | {run.total_latency_ms / 1000:.2f}s |",
        "",
    ]
    if run.deterministic_metrics:
        metrics = run.deterministic_metrics
        lines.extend(
            [
                "## Deterministic Validation Summary",
                "",
                "| Metric | Value |",
                "|---|---:|",
                f"| Detection Precision | {metrics.detection_precision:.3f} |",
                f"| Detection Recall | {metrics.detection_recall:.3f} |",
                f"| Detection F-beta (beta={metrics.beta:g}) | {metrics.detection_f_beta:.3f} |",
                f"| Validated Precision | {metrics.validated_precision:.3f} |",
                f"| Validated Recall | {metrics.validated_recall:.3f} |",
                f"| Validated F-beta (beta={metrics.beta:g}) | {metrics.validated_f_beta:.3f} |",
                f"| Deterministic Pass Rate | {_rate(metrics.deterministic_pass_rate)} |",
                f"| Patch Apply Rate | {_rate(metrics.patch_apply_rate)} |",
                f"| Test Pass Rate | {_rate(metrics.test_pass_rate)} |",
                f"| Structural Pass Rate | {_rate(metrics.structural_pass_rate)} |",
                f"| False Positives / Case | {metrics.false_positives_per_case:.3f} |",
                f"| Cost / Validated Fix | {_cost(metrics.cost_per_validated_fix)} |",
                f"| Latency / Case | {metrics.latency_per_case_ms:.1f}ms |",
                "",
            ]
        )
    lines.extend(["## Case Results", ""])
    for result in run.case_results:
        finding = next(
            (item.finding for item in result.scored_findings if item.is_true_positive), None
        )
        lines.extend(
            [
                f"### {result.case_id}",
                "",
                f"Review Quality Score: {result.score:.1f}/100  ",
                f"Bug Found: {'yes' if result.bug_found else 'no'}  ",
                f"Correct File: {'yes' if result.correct_file else 'no'}  ",
                f"Correct Line: {result.line_match}  ",
                f"False Positives: {result.false_positive_count}",
                "",
                "Ground Truth:  ",
                result.ground_truth_summary,
                "",
                "Reviewer Finding:  ",
                finding.summary if finding else "No matching finding.",
                "",
                "Scoring:",
                f"- Concept Match: {result.breakdown.concept_match:.1f}/35",
                f"- File Match: {result.breakdown.file_match:.1f}/20",
                f"- Line Overlap: {result.breakdown.line_overlap:.1f}/15",
                f"- Severity Match: {result.breakdown.severity_match:.1f}/10",
                f"- Fix Quality: {result.breakdown.fix_quality:.1f}/15",
                f"- False Positive Score: {result.breakdown.no_false_positives:.1f}/5",
                "",
            ]
        )
        if result.deterministic_case_score:
            deterministic = result.deterministic_case_score
            lines.extend(
                [
                    "Deterministic Validation:",
                    f"- Detection: {'pass' if deterministic.detected_bug else 'fail'}",
                    f"- Localization: {'pass' if deterministic.localized_correctly else 'fail'}",
                    f"- Patch Applied: {'yes' if result.patch_applied else 'no'}",
                    f"- Tests: {_status(result.tests_passed, result.tests_ran)}",
                    "- Structural Validators: "
                    + _status(result.validators_passed, bool(result.validators_run)),
                    f"- Deterministic Pass: {'yes' if result.deterministic_pass else 'no'}",
                    (
                        "- Failure Reasons: " + ", ".join(result.failure_reasons)
                        if result.failure_reasons
                        else "- Failure Reasons: none"
                    ),
                ]
            )
            if result.validator_results:
                lines.append("- Validator Evidence:")
                for validator in result.validator_results:
                    lines.append(
                        f"  - {validator['name']}: {'pass' if validator['passed'] else 'fail'} "
                        f"- {validator['message']}"
                    )
            if result.raw_suggested_patch:
                lines.extend(
                    ["", "Suggested Patch:", "```diff", result.raw_suggested_patch.rstrip(), "```"]
                )
            if result.test_stdout_tail or result.test_stderr_tail:
                lines.extend(
                    [
                        "",
                        "Test Output Tail:",
                        "```text",
                        (result.test_stdout_tail + result.test_stderr_tail).rstrip(),
                        "```",
                    ]
                )
            lines.append("")
    false_positives = [
        (result.case_id, item)
        for result in run.case_results
        for item in result.scored_findings
        if not item.is_true_positive
    ]
    missed = [result.case_id for result in run.case_results if not result.bug_found]
    lines.extend(["## False Positive Summary", ""])
    if false_positives:
        lines.extend(
            f"- `{case_id}`: {item.finding.title} ({item.false_positive_reason})"
            for case_id, item in false_positives
        )
    else:
        lines.append("None.")
    lines.extend(["", "## Missed Bug Summary", ""])
    if missed:
        lines.extend(f"- `{case_id}`" for case_id in missed)
    else:
        lines.append("None.")
    lines.extend(
        [
            "",
            "## Cost And Latency Summary",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| Estimated Cost | ${run.total_cost:.4f} |",
            f"| Total Latency | {run.total_latency_ms / 1000:.2f}s |",
            _cost_summary_line(run),
        ]
    )
    return "\n".join(lines)


def write_markdown_report(run: RunResult, output: Path) -> None:
    output.write_text(render_markdown(run) + "\n", encoding="utf-8")


def _rate(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _cost(value: float | None) -> str:
    return f"${value:.4f}" if value is not None else "n/a"


def _status(passed: bool | None, ran: bool) -> str:
    if not ran:
        return "not run"
    return "pass" if passed else "fail"


def _cost_summary_line(run: RunResult) -> str:
    if run.deterministic_metrics:
        return (
            f"| Cost / Validated Fix | {_cost(run.deterministic_metrics.cost_per_validated_fix)} |"
        )
    return (
        f"| Cost / Detected Bug | ${run.total_cost / run.bugs_found:.4f} |"
        if run.bugs_found
        else "| Cost / Detected Bug | n/a |"
    )
