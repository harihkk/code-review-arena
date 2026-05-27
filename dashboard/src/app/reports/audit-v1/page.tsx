import { CodeBlock } from "../../../components/CodeBlock";
import { FailureReasonChart } from "../../../components/FailureReasonChart";
import { PageHeader } from "../../../components/PageHeader";
import { StatusBadge } from "../../../components/StatusBadge";
import { AuditReviewerRow, displayReviewer, loadAuditReport } from "../../../lib/auditReport";

export default function AuditV1ReportPage() {
  const report = loadAuditReport();

  if (!report || report.empty) {
    return (
      <>
        <PageHeader
          eyebrow="Audit Pack v1 report"
          title="Detection Is Not Validation: Audit Pack v1"
          description="A local execution-backed audit of code-review agents on 10 patch-required seeded bugs."
        />
        <section className="panel empty">
          <h2>No audit report data found.</h2>
          <p>Generate local run evidence and a report snapshot to populate this page.</p>
          <CodeBlock compact>{`arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena audit-report runs/ --output docs/reports/audit-v1-results.md`}</CodeBlock>
        </section>
      </>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Audit Pack v1 report"
        title="Detection Is Not Validation: Audit Pack v1"
        description="A local execution-backed audit of code-review agents on 10 patch-required seeded bugs."
      />

      <section className="report-section">
        <h2>Summary</h2>
        <dl className="report-summary">
          <ReportFact term="Cases" value={String(report.summary.case_count)} />
          <ReportFact term="Primary metric" value="validated_f_beta" code />
          <ReportFact term="Baselines present" value={String(report.reviewers.length)} />
          <ReportFact term="Generated at" value={new Date(report.generated_at).toLocaleString()} />
        </dl>
      </section>

      <section className="report-section">
        <div className="row-between">
          <h2>Reviewer comparison</h2>
          <StatusBadge tone="neutral">Generated local run data</StatusBadge>
        </div>
        <p className="section-caption">
          Reference and mock rows are deterministic controls. No external model row is shown unless it exists in the report data.
        </p>
        <ReviewerTable rows={report.reviewers} />
      </section>

      <section className="report-section">
        <h2>Detection-validation gap</h2>
        <div className="table-scroll">
          <table className="data-table dense-table">
            <thead>
              <tr>
                <th>Reviewer</th>
                <th>Detection F-beta</th>
                <th>Validated F-beta</th>
                <th>Gap</th>
                <th>Primary failure mode</th>
              </tr>
            </thead>
            <tbody>
              {report.reviewers.map((row) => (
                <tr key={`${row.reviewer}-${row.model}-${row.mode}-gap`}>
                  <td><code>{displayReviewer(row)}</code></td>
                  <td>{metric(row.detection_f_beta)}</td>
                  <td className="strong-metric">{metric(row.validated_f_beta)}</td>
                  <td>{gap(row)}</td>
                  <td><code>{row.primary_failure_mode ?? "-"}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="report-section panel">
        <h2>Failure modes</h2>
        <FailureReasonChart counts={report.failure_modes} />
      </section>

      <section className="report-section">
        <h2>Case studies</h2>
        {report.case_studies.length === 0 ? (
          <p className="empty-inline">No failing case evidence appears in this generated report.</p>
        ) : (
          <div className="case-studies">
            {report.case_studies.slice(0, 3).map((study) => (
              <article className="panel case-study" key={`${study.case_id}-${study.reviewer}-${study.model}`}>
                <h3><code>{study.case_id}</code></h3>
                <p className="section-caption">Reviewer: <code>{displayReviewer(study)}</code></p>
                <p><strong>Detected:</strong> {study.finding_summary || "No finding summary recorded."}</p>
                <p><strong>Why validation failed:</strong> <code>{study.failure_reasons.join(", ")}</code></p>
                {study.validator_evidence.map((evidence) => (
                  <p key={evidence.name}><strong>Evidence:</strong> {evidence.name}: {evidence.message}</p>
                ))}
                {study.test_stderr_tail ? <p><strong>Test evidence:</strong> <code>{study.test_stderr_tail}</code></p> : null}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="report-section report-two-columns">
        <div className="panel">
          <h2>Reproduce</h2>
          <CodeBlock compact>{report.reproducibility_commands.join("\n")}</CodeBlock>
        </div>
        <div className="panel">
          <h2>Limitations</h2>
          <ul className="list">
            {report.limitations.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      </section>
    </>
  );
}

function ReportFact({ term, value, code = false }: { term: string; value: string; code?: boolean }) {
  return (
    <div className="report-fact">
      <dt>{term}</dt>
      <dd>{code ? <code>{value}</code> : value}</dd>
    </div>
  );
}

function ReviewerTable({ rows }: { rows: AuditReviewerRow[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table dense-table">
        <thead>
          <tr>
            <th>Reviewer</th>
            <th>Model</th>
            <th>Detection F-beta</th>
            <th>Validated F-beta</th>
            <th>Deterministic Pass Rate</th>
            <th>Patch Apply Rate</th>
            <th>Test Pass Rate</th>
            <th>Structural Pass Rate</th>
            <th>False Positives / Case</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.reviewer}-${row.model}-${row.mode}`}>
              <td><code>{displayReviewer(row)}</code></td>
              <td>{row.model || "-"}</td>
              <td>{metric(row.detection_f_beta)}</td>
              <td className="strong-metric">{metric(row.validated_f_beta)}</td>
              <td>{rate(row.deterministic_pass_rate)}</td>
              <td>{rate(row.patch_apply_rate)}</td>
              <td>{rate(row.test_pass_rate)}</td>
              <td>{rate(row.structural_pass_rate)}</td>
              <td>{metric(row.false_positives_per_case)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function rate(value: number | null) {
  return value == null ? "-" : `${(value * 100).toFixed(1)}%`;
}

function metric(value: number | null) {
  return value == null ? "-" : value.toFixed(3);
}

function gap(row: AuditReviewerRow) {
  if (row.detection_f_beta == null || row.validated_f_beta == null) return "-";
  return (row.detection_f_beta - row.validated_f_beta).toFixed(3);
}
