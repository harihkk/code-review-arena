import { CaseCatalog } from "../../components/CaseCatalog";
import { PageHeader } from "../../components/PageHeader";
import { CaseSummary, fetchJson } from "../../lib/api";

export default async function Cases() {
  const [v1, auditV1] = await Promise.all([
    fetchJson<CaseSummary[]>("/cases?benchmark_set=v1").catch(() => []),
    fetchJson<CaseSummary[]>("/cases?benchmark_set=audit_v1").catch(() => []),
  ]);
  return (
    <>
      <PageHeader
        eyebrow="Dataset"
        title="Benchmark cases"
        description="Browse seeded pull-request bugs, execution requirements, and structural validation used by each benchmark pack."
      />
      <CaseCatalog cases={[...auditV1, ...v1]} />
    </>
  );
}
