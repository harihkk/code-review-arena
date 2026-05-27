import { CodeBlock } from "../../../components/CodeBlock";
import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

export default function ReferencePatchesPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Reference Patches" description="Canonical known-good fixes used to validate the audit harness." />
      <DocsLayout>
        <h1>Reference patches</h1>
        <p>
          Every <code>audit_v1</code> case includes a <code>reference.patch</code> file.
          These static unified diffs are canonical known-good fixes: they should apply
          cleanly, pass required regression tests, and satisfy configured validators.
        </p>
        <h2>Two different controls</h2>
        <p>
          <code>reference-patch</code> reads committed patch files beside each case. It
          verifies that readable fixture artifacts still pass the execution pipeline.
        </p>
        <p>
          <code>mock:perfect_patch</code> is the deterministic happy path supplied by the
          mock reviewer implementation. It tests reviewer plumbing separately from the
          stored reference artifacts.
        </p>
        <h2>Run the baseline</h2>
        <CodeBlock compact>arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution</CodeBlock>
      </DocsLayout>
    </>
  );
}
