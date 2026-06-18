"""Standalone HTML benchmark report renderer."""

from html import escape
from pathlib import Path

from arena.core.models import CaseResult, RunResult


def render_html(run: RunResult) -> str:
    rows = "".join(
        "<tr>"
        f"<td><a href='#{escape(item.case_id)}'>{escape(item.case_id)}</a></td>"
        f"<td>{item.score:.1f}</td><td>{'Yes' if item.bug_found else 'No'}</td>"
        f"<td>{item.false_positive_count}</td><td>{escape(item.line_match)}</td>"
        f"<td>{_pass(item.deterministic_pass)}</td>"
        "</tr>"
        for item in run.case_results
    )
    detail_sections = []
    for item in run.case_results:
        true_positive = next(
            (finding.finding for finding in item.scored_findings if finding.is_true_positive),
            None,
        )
        extras = [
            f"<li>{escape(finding.finding.title)} "
            f"({escape(finding.false_positive_reason or 'unmatched')})</li>"
            for finding in item.scored_findings
            if not finding.is_true_positive
        ]
        detail_sections.append(
            f"""<article id="{escape(item.case_id)}">
<h3>{escape(item.case_id)} <span class="score">quality {item.score:.1f}/100</span></h3>
<p><strong>Ground truth:</strong> {escape(item.ground_truth_summary)}</p>
<p><strong>Finding:</strong> {escape(true_positive.summary) if true_positive else "Missed."}</p>
<h4>Scoring breakdown</h4>
<div class="breakdown">
<span>Concept {item.breakdown.concept_match:.1f}/35</span>
<span>File {item.breakdown.file_match:.1f}/20</span>
<span>Line {item.breakdown.line_overlap:.1f}/15</span>
<span>Severity {item.breakdown.severity_match:.1f}/10</span>
<span>Fix {item.breakdown.fix_quality:.1f}/15</span>
</div>
{("<p><strong>False positives:</strong></p><ul>" + "".join(extras) + "</ul>") if extras else ""}
{_deterministic_detail(item)}
</article>"""
        )
    missed = [item.case_id for item in run.case_results if not item.bug_found]
    false_positive_summary = [
        f"{item.case_id}: {finding.finding.title} ({finding.false_positive_reason})"
        for item in run.case_results
        for finding in item.scored_findings
        if not finding.is_true_positive
    ]
    fp_items = (
        "".join(f"<li>{escape(text)}</li>" for text in false_positive_summary) or "<li>None</li>"
    )
    missed_items = "".join(f"<li>{escape(case_id)}</li>" for case_id in missed) or "<li>None</li>"
    deterministic_cards = ""
    if run.deterministic_metrics:
        metrics = run.deterministic_metrics
        deterministic_cards = f"""<h2>Deterministic Validation Summary</h2>
<section class="cards">
<div class="card"><span class="value">{metrics.validated_case_rate:.3f}</span>
Validated case rate</div>
<div class="card"><span class="value">{metrics.detection_f_beta:.3f}</span>Detection F-beta</div>
<div class="card"><span class="value">{_rate(metrics.deterministic_pass_rate)}</span>
Validated passes</div>
<div class="card"><span class="value">{_rate(metrics.patch_apply_rate)}</span>Patch apply</div>
<div class="card"><span class="value">{_rate(metrics.test_pass_rate)}</span>Tests</div>
<div class="card"><span class="value">{_rate(metrics.structural_pass_rate)}</span>Structural</div>
<div class="card"><span class="value">{metrics.false_positives_per_case:.2f}</span>
False positives / case</div>
<div class="card"><span class="value">{_cost(metrics.cost_per_validated_fix)}</span>
Cost / validated fix</div>
<div class="card"><span class="value">{metrics.latency_per_case_ms:.1f}ms</span>Latency / case</div>
</section>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>CodeReview Arena - {escape(run.run_id)}</title>
<style>
body {{ font: 15px system-ui, sans-serif; max-width: 1000px; margin: 2rem auto; color: #16202a; }}
.cards {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0 2rem; }}
.card {{ background: #f3f6f8; padding: 1rem; border-radius: 8px; min-width: 130px; }}
.value {{ font-size: 1.7rem; font-weight: bold; display: block; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ padding: .65rem; border-bottom: 1px solid #ddd; text-align: left; }}
a {{ color: #155eef; }}
article {{ border: 1px solid #e4e9ef; border-radius: 10px; padding: 1rem; margin: 1rem 0; }}
.score {{ color: #155eef; font-size: .9em; margin-left: .5rem; }}
.breakdown {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
.breakdown span {{ background: #eef4ff; border-radius: 999px; padding: .35rem .65rem; }}
pre {{ overflow: auto; background: #101827; color: #e8edf5; padding: .9rem; border-radius: 8px; }}
</style></head><body>
<h1>CodeReview Arena Report</h1>
<p>{escape(run.reviewer)}:{escape(run.model or "")} on
{escape(run.benchmark_set)} - {escape(run.run_id)}</p>
<section class="cards">
<div class="card"><span class="value">{run.total_score:.1f}</span>Review quality</div>
<div class="card"><span class="value">{run.bugs_found}/{run.case_count}</span>Bugs found</div>
<div class="card"><span class="value">{run.false_positives}</span>False positives</div>
<div class="card"><span class="value">${run.total_cost:.4f}</span>Est. cost</div>
</section>
{deterministic_cards}
<h2>Cases</h2><table><thead><tr><th>Case</th><th>Score</th><th>Found</th>
<th>False positives</th><th>Line match</th><th>Deterministic</th></tr></thead>
<tbody>{rows}</tbody></table>
<h2>False Positive Summary</h2><ul>{fp_items}</ul>
<h2>Missed Bug Summary</h2><ul>{missed_items}</ul>
<h2>Case Traces</h2>{"".join(detail_sections)}
</body></html>"""


def write_html_report(run: RunResult, output: Path) -> None:
    output.write_text(render_html(run), encoding="utf-8")


def _pass(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "Pass" if value else "Fail"


def _rate(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _cost(value: float | None) -> str:
    return f"${value:.4f}" if value is not None else "n/a"


def _deterministic_detail(item: CaseResult) -> str:
    if not item.deterministic_case_score:
        return ""
    validators = item.validator_results
    validator_items = "".join(
        f"<li>{escape(str(result['name']))}: {_pass(bool(result['passed']))} - "
        f"{escape(str(result['message']))}</li>"
        for result in validators
    )
    reasons = ", ".join(item.failure_reasons) or "none"
    patch = item.raw_suggested_patch or "(no patch supplied)"
    tests = item.test_stdout_tail + item.test_stderr_tail
    test_details = (
        "<details><summary>Test output tail</summary><pre>" + escape(tests) + "</pre></details>"
        if tests
        else ""
    )
    return f"""<h4>Deterministic validation</h4>
<p>Patch applied: <strong>{_pass(item.patch_applied)}</strong> |
Tests: <strong>{_pass(item.tests_passed)}</strong> |
Structural: <strong>{_pass(item.validators_passed)}</strong> |
Result: <strong>{_pass(item.deterministic_pass)}</strong></p>
<p><strong>Failure reasons:</strong> {escape(reasons)}</p>
{("<ul>" + validator_items + "</ul>") if validator_items else ""}
<details><summary>Suggested patch</summary><pre>{escape(patch)}</pre></details>
{test_details}"""
