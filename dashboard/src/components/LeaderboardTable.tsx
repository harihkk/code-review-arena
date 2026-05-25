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
  | "false_positives_per_case"
  | "cost_per_validated_fix"
  | "latency_per_case_ms";

const metricOptions: Metric[] = [
  "validated_f_beta",
  "detection_f_beta",
  "deterministic_pass_rate",
  "patch_apply_rate",
  "structural_pass_rate",
  "test_pass_rate",
  "false_positives_per_case",
  "cost_per_validated_fix",
  "latency_per_case_ms",
];

export function LeaderboardTable({ rows }: { rows: LeaderboardRow[] }) {
  const [metric, setMetric] = useState<Metric>("validated_f_beta");
  const [beta, setBeta] = useState(1);
  const ascending = metric === "false_positives_per_case" || metric === "cost_per_validated_fix" || metric === "latency_per_case_ms";
  const sorted = useMemo(
    () => [...rows].sort((left, right) => {
      const leftValue = value(left, metric, beta);
      const rightValue = value(right, metric, beta);
      if (leftValue == null) return rightValue == null ? 0 : 1;
      if (rightValue == null) return -1;
      const delta = leftValue - rightValue;
      return ascending ? delta : -delta;
    }),
    [ascending, beta, metric, rows],
  );
  if (!rows.length) return <div className="panel empty">No completed runs yet.</div>;
  return (
    <>
      <div className="controls panel">
        <label>
          Ranking metric
          <select value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>
            {metricOptions.map((option) => <option value={option} key={option}>{option}</option>)}
          </select>
        </label>
        <label>
          Beta
          <select value={beta} onChange={(event) => setBeta(Number(event.target.value))}>
            <option value={0.5}>0.5 Precision mode</option>
            <option value={1}>1.0 Balanced</option>
            <option value={2}>2.0 Recall mode</option>
          </select>
        </label>
        <span className="control-note">Primary ranking: <strong>validated_f_beta</strong></span>
      </div>
      <div className="table-scroll">
        <table className="data-table leaderboard-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Reviewer / Model</th>
              <th>Mode</th>
              <th>Status</th>
              <th className="numeric">Validated F-beta</th>
              <th className="numeric">Detection F-beta</th>
              <th className="numeric">Passes</th>
              <th className="numeric">Patch Apply</th>
              <th className="numeric">Structural</th>
              <th className="numeric">Tests</th>
              <th className="numeric">False Positives</th>
              <th className="numeric">Cost</th>
              <th className="numeric">Latency</th>
              <th>Run Date</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, index) => {
              const metrics = row.deterministic_metrics;
              return (
                <tr key={`${row.run_id}:${row.mode}`}>
                  <td className="numeric">{index + 1}</td>
                  <td>
                    <Link href={`/runs/${row.run_id}`}><strong>{row.reviewer}</strong></Link>
                    <div className="table-subtitle">{row.model || "default model"}</div>
                  </td>
                  <td>{row.mode}</td>
                  <td>{validationBadge(row)}</td>
                  <td className="numeric strong-metric">{formatRate(dynamicF(metrics, "validated", beta))}</td>
                  <td className="numeric">{formatRate(dynamicF(metrics, "detection", beta))}</td>
                  <td className="numeric">{row.deterministic_passes}/{row.case_count}</td>
                  <td className="numeric">{formatRate(metrics?.patch_apply_rate)}</td>
                  <td className="numeric">{formatRate(metrics?.structural_pass_rate)}</td>
                  <td className="numeric">{formatRate(metrics?.test_pass_rate)}</td>
                  <td className="numeric">{row.false_positives}</td>
                  <td className="numeric">${row.cost.toFixed(4)}</td>
                  <td className="numeric">{(row.latency_ms / 1000).toFixed(2)}s</td>
                  <td>{new Date(row.completed_at).toLocaleDateString()}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
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
  if (!metrics) return <StatusBadge tone="neutral">Review only</StatusBadge>;
  if (metrics.validated_f_beta === 1 && row.false_positives === 0) {
    return <StatusBadge tone="success">Validated</StatusBadge>;
  }
  if (metrics.detection_f_beta > metrics.validated_f_beta) {
    return (
      <div className="status-stack">
        <StatusBadge tone="warning">Detected only - fix not validated</StatusBadge>
        {secondaryFailure(row)}
      </div>
    );
  }
  if (row.false_positives > 0) return <StatusBadge tone="danger">Noisy</StatusBadge>;
  return <StatusBadge tone="danger">Validation failed</StatusBadge>;
}

function secondaryFailure(row: LeaderboardRow) {
  const metrics = row.deterministic_metrics;
  if (!metrics) return null;
  if (row.false_positives > 0) return <StatusBadge tone="danger">Noisy</StatusBadge>;
  if (metrics.patch_apply_rate == null) return <StatusBadge tone="danger">No patch</StatusBadge>;
  if (metrics.patch_apply_rate === 0) return <StatusBadge tone="danger">Patch failed</StatusBadge>;
  if (metrics.structural_pass_rate === 0) return <StatusBadge tone="danger">Validator failed</StatusBadge>;
  return null;
}

function formatRate(value: number | null | undefined) {
  return value == null ? "-" : value.toFixed(3);
}
