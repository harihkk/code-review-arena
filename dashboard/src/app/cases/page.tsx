import { CaseCatalog } from "../../components/CaseCatalog";
import { PageHeader } from "../../components/PageHeader";
import { CaseSummary, fetchJson } from "../../lib/api";

export default async function Cases() {
  const cases = await fetchJson<CaseSummary[]>("/cases").catch(() => []);
  return (
    <>
      <PageHeader
        eyebrow="Benchmark set v1"
        title="Seeded production bugs"
        description="Ten curated pull requests covering security, correctness, performance, reliability, distributed systems, frontend behavior, API compatibility, and AI quality."
      />
      <CaseCatalog cases={cases} />
    </>
  );
}
