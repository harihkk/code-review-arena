import Link from "next/link";

import { CodeBlock } from "../../../components/CodeBlock";
import { FailureReasonChart } from "../../../components/FailureReasonChart";
import { shortFailureLabel } from "../../../components/FailureReasonList";
import { PageHeader } from "../../../components/PageHeader";
import { StatusBadge } from "../../../components/StatusBadge";
import {
  AuditReport,
  AuditReviewerRow,
  readAuditReport,
} from "../../../lib/auditReport";
import {
  CONTROL_BASELINE_NOTE,
  reviewerDisplayName,
} from "../../../lib/reviewers";

type CaseStudy = AuditReport["case_studies"][number];

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
          <p>
            Generate local run evidence and a report snapshot to populate this
            page.
          </p>
          <CodeBlock
            compact
          >{`arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
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
          <ReportFact term="Primary metric" value="validated_case_rate" code />
          <ReportFact
            term="Validation"
            value="patch apply + tests + validators"
          />
          <ReportFact term="Source" value="local run artifacts" />
        </dl>
        <p className="section-caption">
          Generated {new Date(report.generated_at).toLocaleString()}
        </p>
      </section>

      <section className="report-section">
        <div className="row-between">
          <h2>Reviewer comparison</h2>
          <StatusBadge tone="neutral">Generated local run data</StatusBadge>
        </div>
        <p className="section-caption">
          {CONTROL_BASELINE_NOTE} No external model row is shown unless it
          exists in the report data.
        </p>
        <ReviewerTable rows={report.reviewers} />
      </section>

      <section className="report-section">
        <h2>Detection-validation gap</h2>
        <div className="gap-bars">
          {report.reviewers.map((row) => (
            <article key={`${row.reviewer}-${row.model}-${row.mode}-gap`}>
              <div className="gap-row-head">
                <span className="reviewer-name">
                  <strong>{reviewerDisplayName(row)}</strong>
                </span>
                <span>Gap {gap(row)}</span>
              </div>
              <MetricBar label="Detection" value={row.detection_f_beta} />
              <MetricBar
                label="Validation"
                value={row.validated_case_rate}
                accent
              />
              <p className="section-caption">
                Primary failure mode:{" "}
                {row.primary_failure_mode
                  ? shortFailureLabel(row.primary_failure_mode)
                  : "None"}
              </p>
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
          <p className="empty-inline">
            No failing case evidence appears in this generated report.
          </p>
        ) : (
          <div className="case-studies">
            {report.case_studies.slice(0, 3).map((study) => (
              <CaseStudyCard
                study={study}
                key={`${study.case_id}-${study.reviewer}-${study.model}`}
              />
            ))}
          </div>
        )}
      </section>

      <section className="report-section">
        <div className="panel reproduce-panel">
          <h2>Reproduce</h2>
          <CodeBlock compact>
            {report.reproducibility_commands.join("\n")}
          </CodeBlock>
        </div>
      </section>

      <section className="report-section">
        <div className="panel">
          <h2>Limitations</h2>
          <ul className="limitations-list">
            {report.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}

function CaseStudyCard({ study }: { study: CaseStudy }) {
  const location = detectedLocation(study.finding_summary);
  return (
    <article className="panel case-study">
      <dl className="case-study-fields">
        <div>
          <dt>Case</dt>
          <dd>
            <Link href={`/cases/${study.case_id}?benchmark_set=audit_v1`}>
              {study.case_id}
            </Link>
          </dd>
        </div>
        <div>
          <dt>Reviewer</dt>
          <dd className="reviewer-name">{reviewerDisplayName(study)}</dd>
        </div>
        {location ? (
          <div>
            <dt>Detected</dt>
            <dd className="file">{location}</dd>
          </div>
        ) : null}
        <div>
          <dt>Validation</dt>
          <dd>
            {study.failure_reasons.length ? (
              <div className="validation-result">
                <span className="failure-text">Failed validation</span>
                <ul className="reason-chips">
                  {study.failure_reasons.map((reason) => (
                    <li key={reason}>{shortFailureLabel(reason)}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <span className="pass-text">Passed all validation stages.</span>
            )}
          </dd>
        </div>
      </dl>
    </article>
  );
}

/** Best-effort extraction of a file-like path from a reviewer's free-text finding summary. */
function detectedLocation(summary: string): string | null {
  const match = summary.match(/\b[\w-]+(?:\/[\w.-]+)*\.[A-Za-z0-9]{1,8}\b/);
  return match ? match[0] : null;
}

function ReportFact({
  term,
  value,
  code = false,
}: {
  term: string;
  value: string;
  code?: boolean;
}) {
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
            <th>
              Detection <span className="nowrap">F-beta</span>
            </th>
            <th>
              Validated <span className="nowrap">rate</span>
            </th>
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
              <td>
                <span className="reviewer-name">
                  <strong>{reviewerDisplayName(row)}</strong>
                </span>
              </td>
              <td>{row.model || "-"}</td>
              <td>{metric(row.detection_f_beta)}</td>
              <td className="strong-metric">{metric(row.validated_case_rate)}</td>
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

function MetricBar({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: number | null;
  accent?: boolean;
}) {
  const percent = Math.max(0, Math.min(1, value ?? 0)) * 100;
  return (
    <div className={`report-bar ${accent ? "accent" : ""}`}>
      <span>{label}</span>
      <i>
        <b style={{ width: `${percent}%` }} />
      </i>
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
  if (row.detection_f_beta == null || row.validated_case_rate == null) return "-";
  return (row.detection_f_beta - row.validated_case_rate).toFixed(3);
}
