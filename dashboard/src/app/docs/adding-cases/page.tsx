import { CodeBlock } from "../../../components/CodeBlock";
import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const structure = `benchmark_sets/v1/new_case/
  case.yaml
  before/
  after/
  pr.diff
  tests/`;

export default function AddingCasesPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Adding Cases" description="Extend the benchmark with a reproducible seeded defect." />
      <DocsLayout>
        <h1>Add a benchmark case</h1>
        <ol>
          <li>Create minimal working <code>before/</code> code and buggy <code>after/</code> code.</li>
          <li>Generate a valid unified <code>pr.diff</code> that exposes the introduced defect.</li>
          <li>Author <code>case.yaml</code> ground truth, localization, scoring, validation, execution, and beta settings.</li>
          <li>Add regression tests when execution can demonstrate the repair.</li>
          <li>Select tolerant structural validators or implement a validator with unit tests.</li>
          <li>Run <code>arena validate benchmark_sets/v1</code> and a deterministic mock-patch full run.</li>
        </ol>
        <CodeBlock compact>{structure}</CodeBlock>
      </DocsLayout>
    </>
  );
}
