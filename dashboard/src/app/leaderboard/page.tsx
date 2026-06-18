import { LeaderboardTable } from "../../components/LeaderboardTable";
import { PageHeader } from "../../components/PageHeader";
import { fetchJson, LeaderboardRow } from "../../lib/api";
import { loadReportLeaderboardRows } from "../../lib/auditReport";

export default async function LeaderboardPage() {
  const liveRows = await fetchJson<LeaderboardRow[]>("/leaderboard").catch(() => []);
  const auditRows = liveRows.some((row) => row.benchmark_set === "audit_v1") ? [] : loadReportLeaderboardRows();
  const rows = [...auditRows, ...liveRows];
  return (
    <>
      <PageHeader
        eyebrow="Results"
        title="Leaderboard"
        description="Runs ranked by validated_case_rate. Detection metrics are shown separately because a review can identify a bug without producing a valid fix."
      />
      <LeaderboardTable rows={rows} />
    </>
  );
}
