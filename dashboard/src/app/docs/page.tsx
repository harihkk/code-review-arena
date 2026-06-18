import Link from "next/link";
import { DocsLayout } from "../../components/DocsLayout";
import { PageHeader } from "../../components/PageHeader";

const pages = [
  ["Getting Started", "/docs/getting-started", "Install, validate, run a deterministic benchmark, and start the API."],
  ["Metrics", "/docs/metrics", "Understand detection_f_beta versus validated_case_rate."],
  ["Audit Pack v1", "/docs/audit-pack-v1", "Harder patch-backed benchmark cases for validation-focused audits."],
  ["Audit Pack v2", "/docs/audit-pack-v2", "A second batch of certified, leak-free logic-defect cases."],
  ["Reference Patches", "/docs/reference-patches", "Understand canonical fixes and deterministic controls."],
  ["Custom Command Reviewer", "/docs/custom-command-reviewer", "Benchmark external agents via subprocess JSON output."],
  ["Validators", "/docs/validators", "See the repair checks used by curated cases."],
  ["Audit Report", "/docs/audit-report", "Generate Markdown and dashboard JSON from audit_v1 runs."],
  ["CLI Reference", "/docs/cli-reference", "Commands for validation, execution, ranking, reports, and serving."],
  ["Troubleshooting", "/docs/troubleshooting", "Resolve common install, report, API, and dashboard issues."],
];

export default function DocsPage() {
  return (
    <>
      <PageHeader eyebrow="Documentation" title="Documentation" description="Run, inspect, and interpret Code Review Arena locally." />
      <DocsLayout>
        <h1>Documentation</h1>
        <div className="docs-cards">
          {pages.map(([title, href, copy]) => (
            <Link className="docs-card" href={href} key={href}>
              <strong>{title}</strong>
              <span>{copy}</span>
            </Link>
          ))}
        </div>
      </DocsLayout>
    </>
  );
}
