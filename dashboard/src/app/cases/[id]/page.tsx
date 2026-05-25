import { DiffViewer } from "../../../components/DiffViewer";
import { PageHeader } from "../../../components/PageHeader";
import { StatusBadge } from "../../../components/StatusBadge";
import { fetchJson } from "../../../lib/api";

type CaseDetail = {
  id: string;
  title: string;
  description: string;
  category: string;
  severity: string;
  stack: string[];
  diff: string;
  validation: {
    patch_required: boolean;
    tests_required: boolean;
    structural_validators: string[];
    max_false_positives: number;
  };
  execution: {
    run_tests: boolean;
    test_command: string | string[] | null;
    timeout_seconds: number;
    docker_image: string | null;
  };
  ground_truth: {
    primary_bug: {
      summary: string;
      concepts: string[];
      files: Array<{ path: string; line_ranges: Array<{ start: number; end: number }> }>;
      acceptable_fix_keywords: string[];
    };
  };
};

export default async function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const item = await fetchJson<CaseDetail>(`/cases/${id}`);
  const bug = item.ground_truth.primary_bug;
  return (
    <>
      <PageHeader
        eyebrow={`${item.category} / ${item.severity}`}
        title={item.title}
        description={item.description}
        actions={<div className="stack">{item.stack.map((tag) => <StatusBadge tone="neutral" key={tag}>{tag}</StatusBadge>)}</div>}
      />
      <div className="trace-grid">
        <section className="panel trace-diff">
          <h2>Pull request diff</h2>
          <DiffViewer diff={item.diff} />
        </section>
        <section className="trace-stack">
          <div className="panel">
            <h2>What this case catches</h2>
            <p>{bug.summary}</p>
            {bug.files.map((file) => <p className="file" key={file.path}>{file.path}:{file.line_ranges.map((range) => `${range.start}-${range.end}`).join(", ")}</p>)}
            <div className="stack">{bug.concepts.map((concept) => <StatusBadge tone="neutral" key={concept}>{concept}</StatusBadge>)}</div>
          </div>
          <div className="panel">
            <h2>Validation configuration</h2>
            <dl className="definition-list">
              <dt>Patch required</dt><dd>{item.validation.patch_required ? "yes" : "no"}</dd>
              <dt>Tests required</dt><dd>{item.validation.tests_required ? "yes" : "no"}</dd>
              <dt>Allowed false positives</dt><dd>{item.validation.max_false_positives}</dd>
              <dt>Test command</dt><dd><code>{String(item.execution.test_command ?? "not configured")}</code></dd>
              <dt>Timeout</dt><dd>{item.execution.timeout_seconds}s</dd>
            </dl>
          </div>
          <div className="panel">
            <h2>Structural validators</h2>
            {item.validation.structural_validators.length ? (
              <div className="stack">{item.validation.structural_validators.map((validator) => <StatusBadge tone="neutral" key={validator}>{validator}</StatusBadge>)}</div>
            ) : <p className="empty-inline">No structural validator configured; execution evidence may still apply.</p>}
          </div>
        </section>
      </div>
    </>
  );
}
