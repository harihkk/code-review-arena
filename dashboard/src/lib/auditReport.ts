import fs from "fs";
import path from "path";

import type { LeaderboardRow } from "./api";

// Must match arena.core.config.REPORT_SCHEMA_VERSION. The producer embeds this in
// the JSON; a mismatch means the dashboard and the CLI are out of step.
export const EXPECTED_REPORT_SCHEMA_VERSION = "1.0";

export type AuditReviewerRow = {
  reviewer: string;
  model: string;
  mode: "review" | "patch" | "full";
  detection_precision: number | null;
  detection_recall: number | null;
  detection_f_beta: number | null;
  validated_precision: number | null;
  validated_recall: number | null;
  validated_f_beta: number | null;
  deterministic_pass_rate: number | null;
  patch_apply_rate: number | null;
  test_pass_rate: number | null;
  structural_pass_rate: number | null;
  false_positives_per_case: number | null;
  cost_per_validated_fix: number | null;
  latency_per_case_ms: number | null;
  run_id: string;
  primary_failure_mode?: string | null;
};

export type AuditReport = {
  schema_version: string;
  generated_at: string;
  empty: boolean;
  summary: {
    benchmark_pack: string;
    run_count: number;
    case_count: number;
    reviewers_tested: string[];
    biggest_detection_validation_gap: { reviewer: string; gap: number } | null;
  };
  reviewers: AuditReviewerRow[];
  failure_modes: Record<string, number>;
  case_studies: Array<{
    case_id: string;
    reviewer: string;
    model: string;
    finding_summary: string;
    failure_reasons: string[];
    validator_evidence: Array<{
      name: string;
      passed: boolean;
      message: string;
    }>;
    test_stderr_tail: string;
  }>;
  reproducibility_commands: string[];
  limitations: string[];
};

export type AuditReportResult = {
  report: AuditReport | null;
  error: string | null;
};

const AUDIT_REPORT_FILE = path.join(
  process.cwd(),
  "public",
  "reports",
  "audit-v1.json",
);
const REGENERATE_HINT = "Regenerate it with `arena audit-report runs/`.";

/**
 * Read the audit report, distinguishing "not generated yet" (report and error both
 * null) from a real failure (error set). Callers that must not show stale or fake
 * data render the error; fallback callers can ignore it and treat null as empty.
 */
export function readAuditReport(): AuditReportResult {
  if (!fs.existsSync(AUDIT_REPORT_FILE)) {
    return { report: null, error: null };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(AUDIT_REPORT_FILE, "utf-8"));
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : String(cause);
    return {
      report: null,
      error: `audit-v1.json is not valid JSON (${detail}). ${REGENERATE_HINT}`,
    };
  }
  const version = (parsed as { schema_version?: unknown }).schema_version;
  if (version !== EXPECTED_REPORT_SCHEMA_VERSION) {
    return {
      report: null,
      error:
        `audit-v1.json schema_version ${JSON.stringify(version)} does not match the ` +
        `expected ${JSON.stringify(EXPECTED_REPORT_SCHEMA_VERSION)}. ${REGENERATE_HINT}`,
    };
  }
  return { report: parsed as AuditReport, error: null };
}

export function loadReportLeaderboardRows(): LeaderboardRow[] {
  const report = readAuditReport().report;
  return (report?.reviewers ?? [])
    .filter(
      (row) =>
        row.detection_precision != null &&
        row.detection_recall != null &&
        row.validated_precision != null &&
        row.validated_recall != null,
    )
    .map((row) => ({
      reviewer: row.reviewer,
      model: row.model,
      mode: row.mode,
      run_id: row.run_id,
      benchmark_set: "audit_v1",
      detail_available: false,
      score: 0,
      bugs_found: 0,
      case_count: report?.summary.case_count ?? 10,
      false_positives: Math.round(
        (row.false_positives_per_case ?? 0) *
          (report?.summary.case_count ?? 10),
      ),
      cost: 0,
      latency_ms:
        (row.latency_per_case_ms ?? 0) * (report?.summary.case_count ?? 10),
      history_count: 1,
      completed_at: report?.generated_at ?? "",
      deterministic_passes: Math.round(
        (row.deterministic_pass_rate ?? 0) * (report?.summary.case_count ?? 10),
      ),
      deterministic_metrics:
        row.detection_f_beta == null || row.validated_f_beta == null
          ? null
          : {
              detection_precision: row.detection_precision!,
              detection_recall: row.detection_recall!,
              detection_f1: row.detection_f_beta,
              detection_f_beta: row.detection_f_beta,
              validated_precision: row.validated_precision!,
              validated_recall: row.validated_recall!,
              validated_f1: row.validated_f_beta,
              validated_f_beta: row.validated_f_beta,
              beta: 1,
              deterministic_pass_rate: row.deterministic_pass_rate ?? 0,
              patch_apply_rate: row.patch_apply_rate,
              test_pass_rate: row.test_pass_rate,
              structural_pass_rate: row.structural_pass_rate,
              false_positives_per_case: row.false_positives_per_case ?? 0,
              cost_per_validated_fix: row.cost_per_validated_fix,
              latency_per_case_ms: row.latency_per_case_ms ?? 0,
            },
    }));
}
