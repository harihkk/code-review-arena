import Link from "next/link";

import { CodeBlock } from "../components/CodeBlock";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { fetchJson, type LeaderboardRow } from "../lib/api";
import { loadReportLeaderboardRows } from "../lib/auditReport";
import { CONTROL_BASELINE_NOTE, reviewerDisplayName } from "../lib/reviewers";

const pipeline = [
  "Seeded PR",
  "Reviewer",
  "Finding JSON",
  "Suggested patch",
  "Patch apply",
  "Tests",
  "Validators",
  "Metrics",
];
const runCommands = `python -m pip install -e ".[dev]"
arena validate benchmark_sets/audit_v1
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0`;
const emptyCommands = `arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0`;

export default async function Home() {
  const liveRows = await fetchJson<LeaderboardRow[]>("/leaderboard").catch(
    () => [],
  );
  const auditRows = liveRows.some((row) => row.benchmark_set === "audit_v1")
    ? []
    : loadReportLeaderboardRows();
  const rows = [...auditRows, ...liveRows];
  const previewRows = rows
    .filter((row) => row.deterministic_metrics)
    .sort(
      (left, right) =>
        (right.deterministic_metrics?.validated_f_beta ?? 0) -
        (left.deterministic_metrics?.validated_f_beta ?? 0),
    )
    .slice(0, 5);

  return (
    <>
      <section className="benchmark-hero">
        <div className="hero-copy-block">
          <p className="eyebrow">Local benchmark for code-review agents</p>
          <h1>Detection is not validation.</h1>
          <p className="hero-subtitle">
            Code Review Arena evaluates whether review agents can find seeded
            pull-request bugs and produce patches that apply, pass tests, and
            satisfy structural validators.
          </p>
          <div className="hero-actions">
            <Link className="button primary" href="/leaderboard">
              View leaderboard
            </Link>
            <Link className="button" href="/methodology">
              Read methodology
            </Link>
            <Link className="button text" href="/docs/getting-started">
              Run locally
            </Link>
          </div>
          <div className="proof-pills" aria-label="Benchmark properties">
            <span>Patch-backed</span>
            <span>Validator-aware</span>
            <span>Local-first</span>
          </div>
        </div>
        <BenchmarkArtifactPanel rows={previewRows} />
      </section>

      <section className="metric-split section-large">
        <div className="section-kicker">Metric split</div>
        <h2>Detection and validation are different signals.</h2>
        <div className="metric-split-grid">
          <article className="metric-panel">
            <span>Detection</span>
            <h3>
              <code>detection_f_beta</code>
            </h3>
            <p>
              Finds and localizes the seeded bug. This can be high even when the
              patch is missing, malformed, or behaviorally wrong.
            </p>
          </article>
          <div className="signal-flow" aria-label="Evaluation flow">
            <span>review comment</span>
            <span>patch</span>
            <span>execution</span>
            <span>validation</span>
          </div>
          <article className="metric-panel primary">
            <span>Validation</span>
            <h3>
              <code>validated_f_beta</code>
            </h3>
            <p>
              Counts fixes that apply cleanly, pass required tests, and satisfy
              structural validators. This is the primary full-mode metric.
            </p>
          </article>
        </div>
      </section>

      <section className="section-large">
        <div className="section-head">
          <div>
            <p className="section-kicker">Results</p>
            <h2>Latest benchmark runs</h2>
          </div>
          <Link href="/leaderboard">Open leaderboard</Link>
        </div>
        {previewRows.length ? (
          <LeaderboardPreview rows={previewRows} />
        ) : (
          <EmptyState
            title="No benchmark runs recorded"
            message="Generate a deterministic baseline locally to populate the leaderboard."
            command={emptyCommands}
          />
        )}
      </section>

      <section className="section-large">
        <div className="section-head">
          <div>
            <p className="section-kicker">Benchmark packs</p>
            <h2>Curated fixtures with deterministic validation.</h2>
          </div>
          <Link href="/cases">Browse cases</Link>
        </div>
        <table className="data-table benchmark-table">
          <thead>
            <tr>
              <th>Pack</th>
              <th>Cases</th>
              <th>Purpose</th>
              <th>Validation</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <code>benchmark_sets/v1</code>
              </td>
              <td>10</td>
              <td>Baseline harness cases</td>
              <td>review scoring + validation</td>
            </tr>
            <tr>
              <td>
                <code>benchmark_sets/audit_v1</code>
              </td>
              <td>10</td>
              <td>Patch-required audit cases</td>
              <td>patch apply + tests + validators</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="section-large">
        <div className="section-head">
          <div>
            <p className="section-kicker">Execution path</p>
            <h2>How a run becomes a benchmark result.</h2>
          </div>
        </div>
        <div className="pipeline">
          {pipeline.map((step, index) => (
            <div className="pipeline-node" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="section-large terminal-section">
        <div>
          <p className="section-kicker">Run locally</p>
          <h2>Reproduce the benchmark controls on your machine.</h2>
          <p>
            Local execution is explicit. Use it with benchmark fixtures you
            trust.
          </p>
        </div>
        <CodeBlock compact label="Terminal">
          {runCommands}
        </CodeBlock>
      </section>
    </>
  );
}

function BenchmarkArtifactPanel({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <aside className="artifact-panel">
      <div className="artifact-header">
        <p>Audit Pack v1</p>
        <strong>10 patch-required cases</strong>
      </div>
      <dl>
        <div>
          <dt>Primary metric</dt>
          <dd>
            <code>validated_f_beta</code>
          </dd>
        </div>
        <div>
          <dt>Validation stages</dt>
          <dd>patch apply, tests, structural validators</dd>
        </div>
        <div>
          <dt>Baselines</dt>
          <dd>Reference Patch, Control: Keyword Gamer, Custom Command</dd>
        </div>
      </dl>
      {rows.length ? (
        <div className="artifact-results">
          <p>Top recorded controls</p>
          {rows.slice(0, 3).map((row, index) => (
            <div key={row.run_id}>
              <span>
                {index + 1}. {reviewerDisplayName(row)}
              </span>
              <strong>
                {row.deterministic_metrics?.validated_f_beta.toFixed(3)}
              </strong>
            </div>
          ))}
          <p className="artifact-note">{CONTROL_BASELINE_NOTE}</p>
        </div>
      ) : (
        <CodeBlock compact label="Generate runs">
          {emptyCommands}
        </CodeBlock>
      )}
    </aside>
  );
}

function LeaderboardPreview({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table preview-table">
        <thead>
          <tr>
            <th className="numeric">Rank</th>
            <th>Reviewer</th>
            <th>Benchmark</th>
            <th className="numeric">
              Detection <span className="nowrap">F-beta</span>
            </th>
            <th className="numeric">
              Validated <span className="nowrap">F-beta</span>
            </th>
            <th className="numeric">Passes</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const metrics = row.deterministic_metrics!;
            const detectedOnly =
              metrics.detection_f_beta >= 0.8 &&
              metrics.validated_f_beta <= 0.3;
            return (
              <tr
                key={row.run_id}
                style={{ animationDelay: `${index * 40}ms` }}
              >
                <td className="numeric">{index + 1}</td>
                <td>
                  <strong>{reviewerDisplayName(row)}</strong>
                </td>
                <td>
                  <code>{row.benchmark_set ?? "recorded"}</code>
                </td>
                <td className="numeric">
                  {metrics.detection_f_beta.toFixed(3)}
                </td>
                <td className="numeric strong-metric">
                  {metrics.validated_f_beta.toFixed(3)}
                </td>
                <td className="numeric">
                  {row.deterministic_passes}/{row.case_count}
                </td>
                <td>
                  <StatusBadge
                    tone={
                      detectedOnly
                        ? "warning"
                        : metrics.validated_f_beta >= 0.8
                          ? "success"
                          : "danger"
                    }
                  >
                    {detectedOnly
                      ? "detected only"
                      : metrics.validated_f_beta >= 0.8
                        ? "validated"
                        : "not validated"}
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
