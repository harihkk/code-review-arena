import { AuditReportView } from "../../../components/AuditReportView";
import { CodeBlock } from "../../../components/CodeBlock";
import { PageHeader } from "../../../components/PageHeader";
import { readAuditReport } from "../../../lib/auditReport";

const DESCRIPTION =
  "A local execution-backed audit on 10 certified logic-defect cases, contrasting the verified reference patch with a generic adversarial baseline.";

export default function AuditV2ReportPage() {
  const { report, error } = readAuditReport("audit-v2.json");

  if (error) {
    return (
      <>
        <PageHeader eyebrow="Audit Pack v2" title="Detection Is Not Validation" description={DESCRIPTION} />
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
        <PageHeader eyebrow="Audit Pack v2" title="Detection Is Not Validation" description={DESCRIPTION} />
        <section className="panel empty">
          <h2>No audit report data found.</h2>
          <p>Generate local run evidence and a report snapshot to populate this page.</p>
          <CodeBlock
            compact
          >{`arena run benchmark_sets/audit_v2 --reviewer reference-patch --mode full --allow-local-execution
arena run benchmark_sets/audit_v2 --reviewer shallow-patch --mode full --allow-local-execution
arena audit-report runs/ --output docs/reports/audit-v2-results.md --json-output dashboard/public/reports/audit-v2.json --benchmark-set audit_v2`}</CodeBlock>
        </section>
      </>
    );
  }

  return (
    <>
      <PageHeader eyebrow="Audit Pack v2" title="Detection Is Not Validation" description={DESCRIPTION} />
      <AuditReportView report={report} packId="audit_v2" />
    </>
  );
}
