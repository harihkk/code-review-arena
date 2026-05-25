import { CodeBlock } from "../../../components/CodeBlock";
import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const schema = `{
  "findings": [{
    "title": "specific production bug",
    "file": "path/to/file.py",
    "line_start": 1,
    "line_end": 4,
    "suggested_fix": "natural language repair",
    "suggested_patch": "diff --git ...",
    "patch_confidence": 0.88,
    "confidence": 0.91
  }],
  "overall_risk": "high",
  "review_summary": "short summary"
}`;

export default function AddingReviewersPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Adding Reviewers" description="Connect a reviewer while preserving deterministic output parsing." />
      <DocsLayout>
        <h1>Reviewer interface</h1>
        <p>Implement <code>BaseReviewer.review(case_context) -&gt; ReviewerResponse</code> and register the adapter. The reviewer receives the diff and contextual evidence, never ground truth.</p>
        <h2>Patch-aware response</h2>
        <p>Responses must be valid JSON without Markdown fences. Natural-language fixes remain supported, but patch/full mode only validates repair outcomes when a unified patch is supplied.</p>
        <CodeBlock compact>{schema}</CodeBlock>
      </DocsLayout>
    </>
  );
}
