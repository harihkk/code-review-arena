"use client";

import { useState } from "react";
import type { CaseTrace } from "../lib/api";
import { DiffViewer } from "./DiffViewer";
import { FailureReasonList } from "./FailureReasonList";
import { FindingCard } from "./FindingCard";
import { JsonViewer } from "./JsonViewer";
import { PatchViewer } from "./PatchViewer";
import { ScoreBreakdownCard } from "./ScoreBreakdownCard";
import { StatusBadge } from "./StatusBadge";
import { ValidatorResultCard } from "./ValidatorResultCard";

const tabs = ["Summary", "Diff", "Patch", "Tests", "Validators", "Raw JSON"] as const;
type Tab = (typeof tabs)[number];

export function TraceTabs({ result }: { result: CaseTrace }) {
  const [tab, setTab] = useState<Tab>("Summary");
  const bug = result.ground_truth.primary_bug;

  return (
    <section className="trace-debugger">
      <div className="tabs" role="tablist" aria-label="Case trace sections">
        {tabs.map((item) => (
          <button
            aria-selected={item === tab}
            className={item === tab ? "active" : undefined}
            key={item}
            onClick={() => setTab(item)}
            role="tab"
            type="button"
          >
            {item}
          </button>
        ))}
      </div>
      <div className="tab-panel" role="tabpanel">
        {tab === "Summary" ? (
          <div className="trace-summary-grid">
            <section className="panel">
              <h2>Case metadata</h2>
              <dl className="definition-list">
                <dt>Case</dt><dd><code>{result.case_id}</code></dd>
                <dt>Category</dt><dd>{result.category}</dd>
                <dt>Severity</dt><dd>{result.severity}</dd>
                <dt>Expected files</dt><dd>{bug.files.map((file) => file.path).join(", ")}</dd>
              </dl>
            </section>
            <section className="panel">
              <h2>Reviewer finding</h2>
              {result.scored_findings.length ? result.scored_findings.map((item, index) => (
                <FindingCard key={index} finding={item.finding} truePositive={item.is_true_positive} reason={item.false_positive_reason} />
              )) : <p className="empty-inline">No findings returned.</p>}
            </section>
            <section className="panel">
              <h2>Failure reasons</h2>
              <FailureReasonList reasons={result.failure_reasons} />
            </section>
            <ScoreBreakdownCard breakdown={result.breakdown} />
          </div>
        ) : null}
        {tab === "Diff" ? (
          <section className="panel">
            <h2>Pull request diff</h2>
            <DiffViewer diff={result.diff} />
          </section>
        ) : null}
        {tab === "Patch" ? (
          <section className="panel">
            <div className="row-between">
              <h2>Suggested patch</h2>
              <Stage label="Apply result" passed={result.patch_applied} applicable={result.patch_provided} />
            </div>
            <PatchViewer patch={result.raw_suggested_patch} />
            {result.patch_error ? <p className="callout failure">{result.patch_error}</p> : null}
            {result.touched_files.length ? <p className="section-caption">Touched files: {result.touched_files.join(", ")}</p> : null}
          </section>
        ) : null}
        {tab === "Tests" ? (
          <section className="panel">
            <div className="row-between">
              <h2>Test execution</h2>
              <Stage label="Test status" passed={result.tests_passed} applicable={result.tests_ran} />
            </div>
            <pre className="mono-output">{result.test_stdout_tail || result.test_output || "No stdout captured."}{result.test_stderr_tail}</pre>
          </section>
        ) : null}
        {tab === "Validators" ? (
          <section className="panel">
            <h2>Structural validators</h2>
            {result.validator_results.length ? result.validator_results.map((validator) => (
              <ValidatorResultCard key={validator.name} result={validator} />
            )) : <p className="empty-inline">No structural validators ran.</p>}
          </section>
        ) : null}
        {tab === "Raw JSON" ? (
          <JsonViewer value={{ scored_findings: result.scored_findings, breakdown: result.breakdown, failure_reasons: result.failure_reasons }} />
        ) : null}
      </div>
    </section>
  );
}

export function Stage({
  label,
  passed,
  applicable = true,
  skippedLabel = "Skipped",
}: {
  label: string;
  passed: boolean | null;
  applicable?: boolean;
  skippedLabel?: string;
}) {
  return (
    <div className="stage">
      <span>{label}</span>
      {!applicable ? <StatusBadge tone="neutral">{skippedLabel}</StatusBadge> : <StatusBadge tone={passed ? "success" : "danger"}>{passed ? "Pass" : "Fail"}</StatusBadge>}
    </div>
  );
}
