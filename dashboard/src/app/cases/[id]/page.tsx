import { DiffViewer } from "../../../components/DiffViewer";
import { PatchViewer } from "../../../components/PatchViewer";
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
  benchmark_set: "v1" | "audit_v1" | "audit_v2";
  diff: string;
  reference_patch: string | null;
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

export default async function CasePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ benchmark_set?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const requested = query.benchmark_set;
  const benchmarkSet =
    requested === "audit_v1" || requested === "audit_v2" ? requested : "v1";
  const item = await fetchJson<CaseDetail>(`/cases/${id}?benchmark_set=${benchmarkSet}`);
  const bug = item.ground_truth.primary_bug;
  return (
    <>
      <PageHeader
        eyebrow={`${item.benchmark_set} / ${item.category} / ${item.severity}`}
        title={item.title}
        description={item.description}
        actions={<div className="stack">{item.stack.map((tag) => <StatusBadge tone="neutral" key={tag}>{tag}</StatusBadge>)}</div>}
      />
      <div className="trace-grid">
        <section className="panel trace-diff">
          <h2><code>pr.diff</code></h2>
          <DiffViewer diff={item.diff} />
          <h2>Reference patch</h2>
          <PatchViewer patch={item.reference_patch} />
        </section>
        <section className="trace-stack">
          <div className="panel">
            <h2>Description</h2>
            <p>{item.description}</p>
            <h3>Bug type</h3>
            <p>{bug.summary}</p>
            <h3>Files</h3>
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
