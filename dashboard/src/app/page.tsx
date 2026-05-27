import Link from "next/link";

import { CodeBlock } from "../components/CodeBlock";
import { StatusBadge } from "../components/StatusBadge";
import { fetchJson, type LeaderboardRow } from "../lib/api";
import { loadReportLeaderboardRows } from "../lib/auditReport";

const pipeline = ["Seeded PR", "Reviewer", "Structured finding", "Suggested patch", "Apply patch", "Tests", "Validators", "Metrics"];
const commands = `arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0`;

export default async function Home() {
  const liveRows = await fetchJson<LeaderboardRow[]>("/leaderboard").catch(() => []);
  const auditRows = liveRows.some((row) => row.benchmark_set === "audit_v1") ? [] : loadReportLeaderboardRows();
  const rows = [...auditRows, ...liveRows];
  const previewRows = rows
    .filter((row) => row.deterministic_metrics)
    .sort((left, right) => (right.deterministic_metrics?.validated_f_beta ?? 0) - (left.deterministic_metrics?.validated_f_beta ?? 0))
    .slice(0, 5);

  return (
    <>
      <section className="hero">
        <div className="hero-main">
          <p className="eyebrow">Local benchmark</p>
          <h1>Code Review Arena</h1>
          <p className="hero-subtitle">Execution-backed benchmark for AI code-review agents.</p>
          <p className="hero-copy">
            Code Review Arena tests whether review agents can detect seeded pull-request
            bugs and produce patches that apply, pass tests, and satisfy structural validators.
          </p>
          <div className="hero-actions">
            <Link className="button primary" href="/leaderboard">View leaderboard</Link>
            <Link className="button" href="/methodology">Read methodology</Link>
            <Link className="button text" href="/docs/getting-started">Run locally</Link>
          </div>
        </div>
        <BenchmarkSummary />
      </section>

      <section className="thesis-compare" aria-labelledby="detection-validation-heading">
        <div className="thesis-intro">
          <h2 id="detection-validation-heading">Detection is not validation</h2>
          <p>Code Review Arena reports whether a defect was found separately from whether its proposed repair worked.</p>
        </div>
        <div className="definition-column">
          <h3>Detection</h3>
          <ul>
            <li>Finds the seeded bug</li>
            <li>Localizes the affected code</li>
          </ul>
          <code>detection_f_beta</code>
        </div>
        <div className="definition-column">
          <h3>Validation</h3>
          <ul>
            <li>Applies the proposed patch</li>
            <li>Runs required tests and structural validators</li>
          </ul>
          <code>validated_f_beta</code>
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Leaderboard preview</h2>
          <Link href="/leaderboard">Full leaderboard</Link>
        </div>
        {previewRows.length ? <PreviewTable rows={previewRows} /> : (
          <div className="panel empty">
            <h2>No benchmark runs recorded</h2>
            <p>Generate a deterministic baseline locally to populate the leaderboard.</p>
            <CodeBlock compact>{commands}</CodeBlock>
          </div>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Benchmark packs</h2>
          <Link href="/cases">Browse cases</Link>
        </div>
        <table className="data-table benchmark-table">
          <thead>
            <tr><th>Pack</th><th>Cases</th><th>Purpose</th><th>Primary validation</th></tr>
          </thead>
          <tbody>
            <tr><td>benchmark_sets/v1</td><td>10</td><td>Baseline harness cases</td><td>Scoring + validation</td></tr>
            <tr><td>benchmark_sets/audit_v1</td><td>10</td><td>Patch-required audit cases</td><td>Patch + tests + validators</td></tr>
          </tbody>
        </table>
      </section>

      <section className="section">
        <div className="section-head"><h2>How it works</h2></div>
        <div className="pipeline">
          {pipeline.map((step, index) => (
            <div className="pipeline-node" key={step}>
              <span>{step}</span>{index < pipeline.length - 1 && <b>-&gt;</b>}
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function BenchmarkSummary() {
  const facts = [
    ["Primary metric", <code key="metric">validated_f_beta</code>],
    ["Audit pack", "10 patch-required cases"],
    ["Validation", "Patch apply + tests + structural validators"],
    ["Local runner", <code key="cli">arena</code>],
    ["Baselines", "reference-patch, keyword_gamer, custom-command"],
  ];
  return (
    <aside className="benchmark-summary">
      <h2>Benchmark summary</h2>
      <dl>
        {facts.map(([term, detail]) => (
          <div className="summary-row" key={String(term)}>
            <dt>{term}</dt><dd>{detail}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

function PreviewTable({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr><th>Rank</th><th>Reviewer</th><th>Benchmark</th><th>Validated F-beta</th><th>Detection F-beta</th><th>Passes</th><th>Status</th></tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const metrics = row.deterministic_metrics!;
            const reviewer = row.reviewer === "mock" && row.model ? `mock:${row.model}` : row.reviewer;
            const validated = metrics.validated_f_beta;
            const detectedOnly = metrics.detection_f_beta > validated;
            return (
              <tr key={row.run_id}>
                <td>{index + 1}</td>
                <td><strong>{reviewer}</strong></td>
                <td><code>{row.benchmark_set ?? "audit_v1"}</code></td>
                <td className="strong-metric">{validated.toFixed(3)}</td>
                <td>{metrics.detection_f_beta.toFixed(3)}</td>
                <td>{row.deterministic_passes}/{row.case_count}</td>
                <td>
                  <StatusBadge tone={detectedOnly ? "warning" : validated > 0 ? "success" : "danger"}>
                    {detectedOnly ? "detected only" : validated > 0 ? "validated" : "not validated"}
                  </StatusBadge>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
