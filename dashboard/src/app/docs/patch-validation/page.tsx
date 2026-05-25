import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const pipeline = ["reviewer JSON", "suggested_patch", "temporary workspace", "git apply", "tests", "validators", "deterministic outcome"];

export default function PatchValidationPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Patch Validation" description="How a proposed repair becomes deterministic evidence." />
      <DocsLayout>
        <h1>Patch validation pipeline</h1>
        <div className="pipeline docs-pipeline">
          {pipeline.map((stage, index) => <div className="pipeline-node" key={stage}><span>{stage}</span>{index < pipeline.length - 1 && <b>-&gt;</b>}</div>)}
        </div>
        <h2>Workspace isolation</h2>
        <p>The buggy <code>after/</code> snapshot is copied beneath the run workspace. Patches and tests execute against that copy; benchmark fixtures are never edited.</p>
        <h2>Applying a patch</h2>
        <p>A finding may include a unified diff as <code>suggested_patch</code>. Arena applies it with <code>git apply</code>; missing or non-clean patches cannot pass required validation.</p>
        <h2>Execution</h2>
        <p>When configured, regression tests run after a clean patch application and validator checks inspect repair properties. Local execution remains explicit opt-in.</p>
      </DocsLayout>
    </>
  );
}
