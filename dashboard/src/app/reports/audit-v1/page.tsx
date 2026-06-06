import { CodeBlock } from "../../../components/CodeBlock";
import { FailureReasonChart } from "../../../components/FailureReasonChart";
import { PageHeader } from "../../../components/PageHeader";
import { StatusBadge } from "../../../components/StatusBadge";
import { AuditReviewerRow, displayReviewer, readAuditReport } from "../../../lib/auditReport";

export default function AuditV1ReportPage() {
  const { report, error } = readAuditReport();

  if (error) {
    return (
      <>
        <PageHeader
          eyebrow="Audit Pack v1"
          title="Detection Is Not Validation"
          description="A local execution-backed audit of code-review agents on 10 patch-required seeded bugs."
        />
        <section className="panel empty">
          <h2>Report data could not be read</h2>
          <p>{error}</p>
        </section>
      </>
    );
  }

  if (!report || report.empty) {
    return (
      <>
        <PageHeader
          eyebrow="Audit Pack v1"
          title="Detection Is Not Validation"
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
        eyebrow="Audit Pack v1"
        title="Detection Is Not Validation"
        description="A local execution-backed audit of code-review agents on 10 patch-required seeded bugs."
      />

      <section className="report-section">
        <h2>Summary</h2>
        <dl className="report-summary">
          <ReportFact term="Cases" value={String(report.summary.case_count)} />
          <ReportFact term="Primary metric" value="validated_f_beta" code />
          <ReportFact term="Validation" value="patch apply + tests + validators" />
          <ReportFact term="Source" value="local run artifacts" />
        </dl>
        <p className="section-caption">Generated {new Date(report.generated_at).toLocaleString()}</p>
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
        <div className="gap-bars">
          {report.reviewers.map((row) => (
            <article key={`${row.reviewer}-${row.model}-${row.mode}-gap`}>
              <div className="gap-row-head">
                <strong><code>{displayReviewer(row)}</code></strong>
                <span>Gap {gap(row)}</span>
              </div>
              <MetricBar label="Detection" value={row.detection_f_beta} />
              <MetricBar label="Validation" value={row.validated_f_beta} accent />
              <p>Primary failure mode: <code>{row.primary_failure_mode ?? "none"}</code></p>
            </article>
          ))}
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

function MetricBar({ label, value, accent = false }: { label: string; value: number | null; accent?: boolean }) {
  const percent = Math.max(0, Math.min(1, value ?? 0)) * 100;
  return (
    <div className={`report-bar ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <i><b style={{ width: `${percent}%` }} /></i>
      <strong>{metric(value)}</strong>
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
