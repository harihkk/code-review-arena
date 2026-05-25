import Link from "next/link";
import { DocsLayout } from "../../components/DocsLayout";
import { PageHeader } from "../../components/PageHeader";

const pages = [
  ["Getting Started", "/docs/getting-started", "Install, validate, run a deterministic benchmark, and start the API."],
  ["Metrics", "/docs/metrics", "Understand detection_f_beta versus validated_f_beta."],
  ["Patch Validation", "/docs/patch-validation", "Follow patches from JSON response to execution-backed outcome."],
  ["Structural Validators", "/docs/validators", "See the tolerant repair checks used by curated cases."],
  ["Adding Cases", "/docs/adding-cases", "Author a seeded PR with ground truth and validation rules."],
  ["Adding Reviewers", "/docs/adding-reviewers", "Implement the reviewer interface and patch-aware JSON schema."],
  ["GitHub Action", "/docs/github-action", "Run a reproducible audit workflow and preserve reports."],
  ["Audit Pack v1", "/docs/audit-pack-v1", "Harder patch-backed benchmark cases for validation-focused audits."],
  ["Custom Command Reviewer", "/docs/custom-command-reviewer", "Benchmark external agents via subprocess JSON output."],
  ["Audit Report", "/docs/audit-report", "Generate Markdown and dashboard JSON from audit_v1 runs."],
];

export default function DocsPage() {
  return (
    <>
      <PageHeader eyebrow="Documentation" title="Build and audit locally" description="Reference material for running, extending, and interpreting CodeReview Arena." />
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
