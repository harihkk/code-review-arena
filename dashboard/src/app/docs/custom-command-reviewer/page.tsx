import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

export default function CustomCommandReviewerPage() {
  return (
    <>
      <PageHeader
        eyebrow="Docs"
        title="Custom Command Reviewer"
        description="Benchmark external review agents via a subprocess and JSON stdout."
      />
      <DocsLayout>
        <h1>Custom command reviewer</h1>
        <pre className="code-block">{`arena run benchmark_sets/audit_v1 \\
  --reviewer custom-command \\
  --command "python scripts/fake_reviewer.py --case {case_json}" \\
  --mode full \\
  --allow-local-execution \\
  --reviewer-timeout-seconds 120`}</pre>
        <p>
          Serialized case JSON never includes ground truth, scoring weights, validator names, or
          expected line ranges. Commands run with <code>shell=False</code>.
        </p>
      </DocsLayout>
    </>
  );
}
