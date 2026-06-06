import { PageHeader } from "../../../../../components/PageHeader";
import { StatusBadge } from "../../../../../components/StatusBadge";
import { Stage, TraceTabs } from "../../../../../components/TraceTabs";
import { CaseTrace, fetchJson } from "../../../../../lib/api";

export default async function TracePage({ params }: { params: Promise<{ id: string; caseId: string }> }) {
  const { id, caseId } = await params;
  const result = await fetchJson<CaseTrace>(`/runs/${id}/cases/${caseId}`);
  return (
    <>
      <PageHeader
        eyebrow={`Case trace / ${result.category} / ${result.severity}`}
        title={result.case_id}
        description={result.ground_truth_summary}
        actions={<StatusBadge tone={result.deterministic_pass ? "success" : "danger"}>{result.deterministic_pass ? "Deterministic pass" : "Deterministic fail"}</StatusBadge>}
      />
      <section className="status-row panel">
        <Stage label="Detected" passed={result.bug_found} />
        <Stage label="Localized" passed={result.correct_file && result.correct_line} />
        <Stage label="Patch" passed={result.patch_applied} applicable={result.patch_provided} skippedLabel="No patch" />
        <Stage label="Tests" passed={result.tests_passed} applicable={result.tests_ran} />
        <Stage label="Validators" passed={result.validators_passed} applicable={result.validators_run.length > 0} />
        <Stage label="Outcome" passed={result.deterministic_pass} applicable={result.deterministic_pass != null} />
      </section>
      <TraceTabs result={result} />
    </>
  );
}
