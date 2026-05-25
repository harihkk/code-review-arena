import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

export default function AuditReportDocsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Docs"
        title="Audit Report"
        description="Aggregate audit_v1 runs into Markdown and dashboard JSON."
      />
      <DocsLayout>
        <h1>Audit report</h1>
        <pre className="code-block">arena audit-report runs/ --output docs/reports/audit-v1-results.md</pre>
        <p>
          The command reads real <code>runs/*/run.json</code> files for benchmark set
          <code>audit_v1</code> only. It also writes
          <code>dashboard/public/reports/audit-v1.json</code> for the
          <a href="/reports/audit-v1">/reports/audit-v1</a> page.
        </p>
      </DocsLayout>
    </>
  );
}
