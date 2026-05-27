"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { DeterministicMetrics, LeaderboardRow } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

type Metric =
  | "validated_f_beta"
  | "detection_f_beta"
  | "deterministic_pass_rate"
  | "patch_apply_rate"
  | "structural_pass_rate"
  | "test_pass_rate"
  | "false_positives_per_case";

const metricOptions: Metric[] = [
  "validated_f_beta",
  "detection_f_beta",
  "deterministic_pass_rate",
  "patch_apply_rate",
  "structural_pass_rate",
  "test_pass_rate",
  "false_positives_per_case",
];

export function LeaderboardTable({ rows }: { rows: LeaderboardRow[] }) {
  const [metric, setMetric] = useState<Metric>("validated_f_beta");
  const [beta, setBeta] = useState(1);
  const [benchmark, setBenchmark] = useState(
    rows.some((row) => row.benchmark_set === "audit_v1")
      ? "audit_v1"
      : (rows.find((row) => row.benchmark_set)?.benchmark_set ?? ""),
  );
  const [reviewer, setReviewer] = useState("");
  const benchmarkOptions = Array.from(new Set(rows.map((row) => row.benchmark_set).filter((item): item is string => Boolean(item)))).sort();
  const reviewerOptions = Array.from(new Set(rows.map((row) => reviewerName(row)))).sort();
  const ascending = metric === "false_positives_per_case";
  const sorted = useMemo(
    () => rows
      .filter((row) => !row.benchmark_set || row.benchmark_set === benchmark)
      .filter((row) => !reviewer || reviewerName(row) === reviewer)
      .sort((left, right) => {
      const leftValue = value(left, metric, beta);
      const rightValue = value(right, metric, beta);
      if (leftValue == null) return rightValue == null ? 0 : 1;
      if (rightValue == null) return -1;
      const delta = leftValue - rightValue;
      return ascending ? delta : -delta;
    }),
    [ascending, benchmark, beta, metric, reviewer, rows],
  );
  if (!rows.length) return <div className="panel empty"><h2>No completed runs yet</h2><p>Run a benchmark locally to generate leaderboard results.</p></div>;
  return (
    <>
      <div className="controls">
        <label>
          Benchmark set
          <select value={benchmark} onChange={(event) => setBenchmark(event.target.value)}>
            {benchmarkOptions.map((option) => <option value={option} key={option}>{option}</option>)}
          </select>
        </label>
        <label>
          Reviewer
          <select value={reviewer} onChange={(event) => setReviewer(event.target.value)}>
            <option value="">All reviewers</option>
            {reviewerOptions.map((option) => <option value={option} key={option}>{option}</option>)}
          </select>
        </label>
        <label>
          Metric
          <select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>
            {metricOptions.map((option) => <option value={option} key={option}>{option}</option>)}
          </select>
        </label>
        <label>
          Beta
          <select value={beta} onChange={(event) => setBeta(Number(event.target.value))}>
            <option value={0.5}>0.5 precision</option>
            <option value={1}>1.0 balanced</option>
            <option value={2}>2.0 recall</option>
          </select>
        </label>
        <span className="control-note">Primary metric: <code>validated_f_beta</code></span>
      </div>
      {!sorted.length ? <div className="panel empty">No recorded runs match these filters.</div> : <div className="table-scroll">
        <table className="data-table leaderboard-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Reviewer</th>
              <th>Model</th>
              <th>Benchmark</th>
              <th>Mode</th>
              <th className="numeric">Validated F-beta</th>
              <th className="numeric">Detection F-beta</th>
              <th className="numeric">Passes</th>
              <th className="numeric">Patch Apply</th>
              <th className="numeric">Tests</th>
              <th className="numeric">Validators</th>
              <th className="numeric">False Positives</th>
              <th className="numeric">Latency</th>
              <th>Status</th>
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, index) => {
              const metrics = row.deterministic_metrics;
              return (
                <tr key={`${row.run_id}:${row.mode}`}>
                  <td className="numeric">{index + 1}</td>
                  <td>
                    <strong>{reviewerName(row)}</strong>
                  </td>
                  <td>{row.model || "-"}</td>
                  <td>{row.benchmark_set ?? "recorded run"}</td>
                  <td>{row.mode}</td>
                  <td className="numeric strong-metric">{formatRate(dynamicF(metrics, "validated", beta))}</td>
                  <td className="numeric">{formatRate(dynamicF(metrics, "detection", beta))}</td>
                  <td className="numeric">{row.deterministic_passes}/{row.case_count}</td>
                  <td className="numeric">{formatRate(metrics?.patch_apply_rate)}</td>
                  <td className="numeric">{formatRate(metrics?.test_pass_rate)}</td>
                  <td className="numeric">{formatRate(metrics?.structural_pass_rate)}</td>
                  <td className="numeric">{row.false_positives}</td>
                  <td className="numeric">{(row.latency_ms / 1000).toFixed(2)}s</td>
                  <td>{validationBadge(row)}</td>
                  <td>{row.detail_available === false ? <Link href="/reports/audit-v1">Report</Link> : <Link href={`/runs/${row.run_id}`}>View</Link>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>}
      <p className="table-footnote">Sorted by <code>{metric}</code> with beta={beta.toFixed(1)}.</p>
    </>
  );
}

function dynamicF(metrics: DeterministicMetrics | null | undefined, tier: "detection" | "validated", beta: number) {
  if (!metrics) return null;
  const precision = tier === "detection" ? metrics.detection_precision : metrics.validated_precision;
  const recall = tier === "detection" ? metrics.detection_recall : metrics.validated_recall;
  const weight = beta * beta;
  return precision + recall === 0 ? 0 : ((1 + weight) * precision * recall) / (weight * precision + recall);
}

function value(row: LeaderboardRow, metric: Metric, beta: number): number | null {
  const metrics = row.deterministic_metrics;
  if (!metrics) return null;
  if (metric === "detection_f_beta") return dynamicF(metrics, "detection", beta) ?? 0;
  if (metric === "validated_f_beta") return dynamicF(metrics, "validated", beta) ?? 0;
  return metrics[metric];
}

function validationBadge(row: LeaderboardRow) {
  const metrics = row.deterministic_metrics;
  if (!metrics) return <StatusBadge tone="neutral">review only</StatusBadge>;
  if (metrics.detection_f_beta > metrics.validated_f_beta) {
    return <StatusBadge tone="warning">detected only</StatusBadge>;
  }
  if (metrics.validated_f_beta > 0 && row.false_positives === 0) {
    return <StatusBadge tone="success">validated</StatusBadge>;
  }
  return <StatusBadge tone="danger">not validated</StatusBadge>;
}

function formatRate(value: number | null | undefined) {
  return value == null ? "-" : value.toFixed(3);
}

function reviewerName(row: LeaderboardRow) {
  return row.reviewer === "mock" && row.model ? `mock:${row.model}` : row.reviewer;
}
