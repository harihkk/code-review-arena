import fs from "fs";
import path from "path";

import { PageHeader } from "../../../components/PageHeader";

type AuditReport = {
  title: string;
  empty: boolean;
  summary: {
    benchmark_pack: string;
    run_count: number;
    case_count: number;
    reviewers_tested: string[];
    biggest_detection_validation_gap: { reviewer: string; gap: number } | null;
  };
  reviewers: Array<{
    reviewer: string;
    model: string;
    mode: string;
    detection_f_beta: number | null;
    validated_f_beta: number | null;
    deterministic_pass_rate: number | null;
    patch_apply_rate: number | null;
    test_pass_rate: number | null;
    structural_pass_rate: number | null;
    false_positives_per_case: number | null;
    cost_per_validated_fix: number | null;
    latency_per_case_ms: number | null;
  }>;
  gaps: Array<{
    reviewer: string;
    model: string;
    mode: string;
    detection_f_beta: number;
    validated_f_beta: number;
    gap: number;
    run_id: string;
  }>;
  failure_modes: Record<string, number>;
  case_studies: Array<{
    case_id: string;
    reviewer: string;
    model: string;
    finding_summary: string;
    failure_reasons: string[];
    validator_evidence: Array<{ name: string; passed: boolean; message: string }>;
    test_stderr_tail: string;
  }>;
  reproducibility_commands: string[];
  limitations: string[];
};

function loadReport(): AuditReport | null {
  const file = path.join(process.cwd(), "public", "reports", "audit-v1.json");
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf-8")) as AuditReport;
}

function formatRate(value: number | null | undefined): string {
  if (value == null) return "n/a";
  return `${(value * 100).toFixed(1)}%`;
}

function formatMetric(value: number | null | undefined): string {
  if (value == null) return "n/a";
  return value.toFixed(3);
}

export default function AuditV1ReportPage() {
  const report = loadReport();

  if (!report || report.empty) {
    return (
      <>
        <PageHeader
          eyebrow="Audit Report"
          title="Detection Is Not Validation"
          description="No audit report has been generated yet."
        />
        <section className="panel">
          <p>Generate an audit_v1 run and report before viewing this page.</p>
          <pre className="code-block">
{`arena run benchmark_sets/audit_v1 --reviewer mock:perfect_patch --mode full --allow-local-execution
arena audit-report runs/ --output docs/reports/audit-v1-results.md`}
          </pre>
        </section>
      </>
    );
  }

  const gap = report.summary.biggest_detection_validation_gap;

  return (
    <>
      <PageHeader
        eyebrow="Audit Report"
        title="Detection Is Not Validation"
        description="Audit Pack v1 compares detection metrics with execution-backed validation."
      />
      <section className="grid stats">
        <div className="panel">
          <span className="stat-label">Benchmark pack</span>
          <strong className="stat-value">{report.summary.benchmark_pack}</strong>
        </div>
        <div className="panel">
          <span className="stat-label">Runs</span>
          <strong className="stat-value">{report.summary.run_count}</strong>
        </div>
        <div className="panel">
          <span className="stat-label">Cases</span>
          <strong className="stat-value">{report.summary.case_count}</strong>
        </div>
        <div className="panel">
          <span className="stat-label">Largest gap</span>
          <strong className="stat-value">
            {gap ? gap.gap.toFixed(3) : "n/a"}
          </strong>
          <span className="stat-note">{gap?.reviewer ?? "no gap recorded"}</span>
        </div>
      </section>

      <section className="panel">
        <h3>Reviewer comparison</h3>
        <div className="table-wrap">
          <table className="dense-table">
            <thead>
              <tr>
                <th>Reviewer</th>
                <th>Model</th>
                <th>Mode</th>
                <th>Detection F-beta</th>
                <th>Validated F-beta</th>
                <th>Pass rate</th>
                <th>Patch apply</th>
                <th>Tests</th>
                <th>Structural</th>
                <th>FP / case</th>
                <th>Latency / case</th>
              </tr>
            </thead>
            <tbody>
              {report.reviewers.map((row) => (
                <tr key={`${row.reviewer}-${row.model}-${row.mode}`}>
                  <td>{row.reviewer}</td>
                  <td>{row.model}</td>
                  <td>{row.mode}</td>
                  <td>{formatMetric(row.detection_f_beta)}</td>
                  <td>{formatMetric(row.validated_f_beta)}</td>
                  <td>{formatRate(row.deterministic_pass_rate)}</td>
                  <td>{formatRate(row.patch_apply_rate)}</td>
                  <td>{formatRate(row.test_pass_rate)}</td>
                  <td>{formatRate(row.structural_pass_rate)}</td>
                  <td>{row.false_positives_per_case ?? "n/a"}</td>
                  <td>{row.latency_per_case_ms ?? "n/a"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="grid two-columns">
        <div className="panel">
          <h3>Detection vs validation gap</h3>
          {report.gaps.length === 0 ? (
            <p>No runs exceeded the configured gap threshold.</p>
          ) : (
            <ul>
              {report.gaps.map((item) => (
                <li key={item.run_id}>
                  <code>{item.reviewer}:{item.model}</code> ({item.mode}): detection {item.detection_f_beta.toFixed(3)}, validated {item.validated_f_beta.toFixed(3)}, gap {item.gap.toFixed(3)}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="panel">
          <h3>Failure mode breakdown</h3>
          {Object.keys(report.failure_modes).length === 0 ? (
            <p>No failure reasons recorded.</p>
          ) : (
            <ul>
              {Object.entries(report.failure_modes).map(([reason, count]) => (
                <li key={reason}><code>{reason}</code>: {count}</li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="panel">
        <h3>Case studies</h3>
        {report.case_studies.length === 0 ? (
          <p>No failing case studies were available in the generated report.</p>
        ) : (
          report.case_studies.map((study) => (
            <article className="case-study" key={`${study.case_id}-${study.reviewer}`}>
              <h4>{study.case_id}</h4>
              <p><strong>{study.reviewer}:{study.model}</strong></p>
              {study.finding_summary ? <p>{study.finding_summary}</p> : null}
              <p>Failure reasons: {study.failure_reasons.join(", ")}</p>
              {study.validator_evidence.length > 0 ? (
                <ul>
                  {study.validator_evidence.map((item) => (
                    <li key={item.name}>{item.name}: {item.message}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))
        )}
      </section>

      <section className="grid two-columns">
        <div className="panel">
          <h3>Reproducibility</h3>
          <pre className="code-block">{report.reproducibility_commands.join("\n")}</pre>
        </div>
        <div className="panel">
          <h3>Limitations</h3>
          <ul>
            {report.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
