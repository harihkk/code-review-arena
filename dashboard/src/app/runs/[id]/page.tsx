import Link from "next/link";
import { FailureReasonList } from "../../../components/FailureReasonList";
import { MetricCard } from "../../../components/MetricCard";
import { PageHeader } from "../../../components/PageHeader";
import { StatusBadge } from "../../../components/StatusBadge";
import { ValidationFunnel } from "../../../components/ValidationFunnel";
import { fetchJson, RunDetail } from "../../../lib/api";

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await fetchJson<RunDetail>(`/runs/${id}`);
  const metrics = run.deterministic_metrics;
  const reasons = run.case_results.flatMap((result) => result.failure_reasons);
  const reasonCounts = Array.from(
    reasons.reduce((counts, reason) => counts.set(reason, (counts.get(reason) ?? 0) + 1), new Map<string, number>()),
  );
  return (
    <>
      <PageHeader
        eyebrow={`${run.benchmark_set} / ${run.mode} / ${run.run_id}`}
        title={`${run.reviewer}:${run.model || "default"}`}
        description="A complete validation trace from seeded defect detection through patch execution and structural checks."
        actions={<StatusBadge tone={metrics && metrics.validated_f_beta === 1 ? "success" : metrics ? "warning" : "neutral"}>{metrics && metrics.validated_f_beta === 1 ? "Validated" : metrics ? "Detected only - fix not validated" : "Review only"}</StatusBadge>}
      />
      <section className="run-meta panel">
        <span><strong>Completed</strong>{new Date(run.completed_at).toLocaleString()}</span>
        <span><strong>Duration</strong>{(run.total_latency_ms / 1000).toFixed(2)}s</span>
        <span><strong>Prompt version</strong>{run.metadata.prompt_version}</span>
        <span><strong>Commit</strong>{run.metadata.git_commit ?? "not recorded"}</span>
      </section>
      {metrics ? (
        <>
          <section className="metrics-eight">
            <MetricCard label="Validated F-beta" value={metrics.validated_f_beta.toFixed(3)} note={`beta=${metrics.beta}`} />
            <MetricCard label="Detection F-beta" value={metrics.detection_f_beta.toFixed(3)} />
            <MetricCard label="Deterministic Pass Rate" value={rate(metrics.deterministic_pass_rate)} />
            <MetricCard label="Patch Apply Rate" value={rate(metrics.patch_apply_rate)} />
            <MetricCard label="Structural Pass Rate" value={rate(metrics.structural_pass_rate)} />
            <MetricCard label="Test Pass Rate" value={rate(metrics.test_pass_rate)} />
            <MetricCard label="False Positives / Case" value={metrics.false_positives_per_case.toFixed(2)} />
            <MetricCard label="Cost / Validated Fix" value={currency(metrics.cost_per_validated_fix)} />
          </section>
          <section className="panel section-space">
            <h2>Validation funnel</h2>
            <ValidationFunnel cases={run.case_results} />
          </section>
          <section className="grid two-columns section-space">
            <div className="panel">
              <h2>Failure reason breakdown</h2>
              {reasonCounts.length ? (
                <ul className="reason-list">
                  {reasonCounts.map(([reason, count]) => <li key={reason}><code>{reason}</code><strong>{count}</strong></li>)}
                </ul>
              ) : <p className="pass-text">Every case passed deterministic validation.</p>}
            </div>
            <div className="panel">
              <h2>Outcome interpretation</h2>
              {metrics.detection_f_beta > metrics.validated_f_beta ? (
                <p className="callout warning">Detected only - fix not validated. The reviewer identified issues that did not complete execution-backed validation.</p>
              ) : <p className="pass-text">Detection and validated repair outcomes align for this run.</p>}
              <FailureReasonList reasons={Array.from(new Set(reasons))} />
            </div>
          </section>
        </>
      ) : (
        <section className="panel section-space"><p>This review-only run has no patch validation metrics.</p></section>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Case</th>
              <th>Category</th>
              <th>Severity</th>
              <th>Detected</th>
              <th>Localized</th>
              <th>Patch</th>
              <th>Tests</th>
              <th>Validators</th>
              <th>Outcome</th>
              <th>Failure Reasons</th>
            </tr>
          </thead>
          <tbody>
            {run.case_results.map((item) => (
              <tr key={item.case_id}>
                <td><Link href={`/runs/${run.run_id}/cases/${item.case_id}`}><strong>{item.case_id}</strong></Link></td>
                <td>{item.category}</td>
                <td>{item.severity}</td>
                <td>{status(item.bug_found, true)}</td>
                <td>{status(item.correct_file && item.correct_line, true)}</td>
                <td>{status(item.patch_applied, item.patch_provided)}</td>
                <td>{status(item.tests_passed, item.tests_ran)}</td>
                <td>{status(item.validators_passed, item.validators_run.length > 0)}</td>
                <td>{status(item.deterministic_pass, item.deterministic_pass != null)}</td>
                <td className="failure-cell">{item.failure_reasons.join(", ") || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function status(value: boolean | null, applicable: boolean) {
  if (!applicable) return <StatusBadge tone="neutral">Skipped</StatusBadge>;
  return <StatusBadge tone={value ? "success" : "danger"}>{value ? "Pass" : "Fail"}</StatusBadge>;
}

function rate(value: number | null) {
  return value == null ? "-" : `${(value * 100).toFixed(1)}%`;
}

function currency(value: number | null) {
  return value == null ? "-" : `$${value.toFixed(4)}`;
}
