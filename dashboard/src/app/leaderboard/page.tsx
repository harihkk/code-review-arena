import { LeaderboardTable } from "../../components/LeaderboardTable";
import { MetricCard } from "../../components/MetricCard";
import { PageHeader } from "../../components/PageHeader";
import { fetchJson, LeaderboardRow } from "../../lib/api";

export default async function LeaderboardPage() {
  const rows = await fetchJson<LeaderboardRow[]>("/leaderboard").catch(() => []);
  const usable = rows.filter((row) => row.deterministic_metrics);
  const highest = (field: "validated_f_beta" | "deterministic_pass_rate" | "patch_apply_rate") =>
    usable.reduce((best, row) => Math.max(best, row.deterministic_metrics?.[field] ?? 0), 0);
  const lowest = (field: "false_positives_per_case" | "cost_per_validated_fix") => {
    const values = usable
      .map((row) => row.deterministic_metrics?.[field])
      .filter((value): value is number => value != null);
    return values.length ? Math.min(...values) : null;
  };
  return (
    <>
      <PageHeader
        eyebrow="Primary benchmark leaderboard"
        title="Validated outcomes"
        description="Full and patch-mode runs rank by whether detected issues became validated repairs. Detection-only scores remain visible as secondary evidence."
      />
      <section className="metrics-five">
        <MetricCard label="Best Validated F-beta" value={highest("validated_f_beta").toFixed(3)} />
        <MetricCard label="Highest Deterministic Pass Rate" value={percent(highest("deterministic_pass_rate"))} />
        <MetricCard label="Best Patch Apply Rate" value={percent(highest("patch_apply_rate"))} />
        <MetricCard label="Lowest False Positives / Case" value={lowest("false_positives_per_case")?.toFixed(2) ?? "-"} />
        <MetricCard label="Lowest Cost / Validated Fix" value={currency(lowest("cost_per_validated_fix"))} />
      </section>
      <LeaderboardTable rows={rows} />
    </>
  );
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function currency(value: number | null) {
  return value == null ? "-" : `$${value.toFixed(4)}`;
}
