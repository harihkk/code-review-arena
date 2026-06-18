import { AuditReportView } from "../../../components/AuditReportView";
import { CodeBlock } from "../../../components/CodeBlock";
import { PageHeader } from "../../../components/PageHeader";
import { readAuditReport } from "../../../lib/auditReport";

const DESCRIPTION =
  "A local execution-backed audit of code-review agents on 10 patch-required seeded bugs.";

export default function AuditV1ReportPage() {
  const { report, error } = readAuditReport("audit-v1.json");

  if (error) {
    return (
      <>
        <PageHeader eyebrow="Audit Pack v1" title="Detection Is Not Validation" description={DESCRIPTION} />
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
        <PageHeader eyebrow="Audit Pack v1" title="Detection Is Not Validation" description={DESCRIPTION} />
        <section className="panel empty">
          <h2>No audit report data found.</h2>
          <p>Generate local run evidence and a report snapshot to populate this page.</p>
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
      <PageHeader eyebrow="Audit Pack v1" title="Detection Is Not Validation" description={DESCRIPTION} />
      <AuditReportView report={report} packId="audit_v1" />
    </>
  );
}
