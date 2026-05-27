import { DiffViewer } from "../../../../../components/DiffViewer";
import { FailureReasonList } from "../../../../../components/FailureReasonList";
import { FindingCard } from "../../../../../components/FindingCard";
import { JsonViewer } from "../../../../../components/JsonViewer";
import { PageHeader } from "../../../../../components/PageHeader";
import { PatchViewer } from "../../../../../components/PatchViewer";
import { ScoreBreakdownCard } from "../../../../../components/ScoreBreakdownCard";
import { StatusBadge } from "../../../../../components/StatusBadge";
import { ValidatorResultCard } from "../../../../../components/ValidatorResultCard";
import { CaseTrace, fetchJson } from "../../../../../lib/api";

export default async function TracePage({ params }: { params: Promise<{ id: string; caseId: string }> }) {
  const { id, caseId } = await params;
  const result = await fetchJson<CaseTrace>(`/runs/${id}/cases/${caseId}`);
  const bug = result.ground_truth.primary_bug;
  return (
    <>
      <PageHeader
        eyebrow={`Case trace / ${result.category} / ${result.severity}`}
        title={result.case_id}
        description={result.ground_truth_summary}
        actions={<StatusBadge tone={result.deterministic_pass ? "success" : "danger"}>{result.deterministic_pass ? "Deterministic pass" : "Deterministic fail"}</StatusBadge>}
      />
      <section className="status-row panel">
        <Stage label="Detection" passed={result.bug_found} />
        <Stage label="Localization" passed={result.correct_file && result.correct_line} />
        <Stage label="Patch Applied" passed={result.patch_applied} applicable={result.patch_provided} skippedLabel="No patch" />
        <Stage label="Tests" passed={result.tests_passed} applicable={result.tests_ran} />
        <Stage label="Validators" passed={result.validators_passed} applicable={result.validators_run.length > 0} />
        <Stage label="Deterministic Outcome" passed={result.deterministic_pass} applicable={result.deterministic_pass != null} />
      </section>
      <div className="trace-grid">
        <section className="panel trace-diff">
          <h2>Pull request diff</h2>
          <DiffViewer diff={result.diff} />
          <p className="section-caption">Expected location: {bug.files.map((file) => `${file.path}:${file.line_ranges.map((range) => `${range.start}-${range.end}`).join(",")}`).join(" | ")}</p>
        </section>
        <section className="trace-stack">
          <section className="panel">
            <h2>Case summary</h2>
            <p>{bug.summary}</p>
            <div className="stack">{bug.concepts.map((concept) => <StatusBadge tone="neutral" key={concept}>{concept}</StatusBadge>)}</div>
          </section>
          <section className="panel">
            <h2>Reviewer finding</h2>
            <div className="trace-stack">
              {result.scored_findings.length ? result.scored_findings.map((item, index) => (
                <FindingCard key={index} finding={item.finding} truePositive={item.is_true_positive} reason={item.false_positive_reason} />
              )) : <p className="empty-inline">No findings returned.</p>}
            </div>
          </section>
          <ScoreBreakdownCard breakdown={result.breakdown} />
        </section>
        <section className="panel full-width">
          <div className="row-between">
            <h2>Suggested patch</h2>
            <Stage label="Apply result" passed={result.patch_applied} applicable={result.patch_provided} />
          </div>
          <PatchViewer patch={result.raw_suggested_patch} />
          {result.patch_error && <p className="callout failure">{result.patch_error}</p>}
          {result.touched_files.length > 0 && <p className="section-caption">Touched files: {result.touched_files.join(", ")}</p>}
        </section>
        <section className="panel">
          <h2>Test execution</h2>
          <Stage label="Test status" passed={result.tests_passed} applicable={result.tests_ran} />
          <pre className="mono-output">{result.test_stdout_tail || result.test_output || "No stdout captured."}{result.test_stderr_tail}</pre>
        </section>
        <section className="panel">
          <h2>Structural validators</h2>
          {result.validator_results.length ? result.validator_results.map((validator) => (
            <ValidatorResultCard key={validator.name} result={validator} />
          )) : <p className="empty-inline">No structural validators ran.</p>}
        </section>
        <section className="panel full-width outcome-panel">
          <h2>Final outcome</h2>
          {result.failure_reasons.length > 0 ? <p className="callout failure">This case failed validation. The evidence below identifies the first repair requirements that were not satisfied.</p> : null}
          <FailureReasonList reasons={result.failure_reasons} />
        </section>
        <section className="panel full-width">
          <h2>Structured finding evidence</h2>
          <JsonViewer value={result.scored_findings} />
        </section>
      </div>
    </>
  );
}

function Stage({ label, passed, applicable = true, skippedLabel = "Skipped" }: { label: string; passed: boolean | null; applicable?: boolean; skippedLabel?: string }) {
  return (
    <div className="stage">
      <span>{label}</span>
      {!applicable ? <StatusBadge tone="neutral">{skippedLabel}</StatusBadge> : <StatusBadge tone={passed ? "success" : "danger"}>{passed ? "Pass" : "Fail"}</StatusBadge>}
    </div>
  );
}
