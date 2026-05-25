import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const validators = [
  "fastapi_requires_admin_authorization",
  "fastapi_tenant_admin_authorization",
  "kafka_idempotency_guard",
  "redis_cache_key_has_tenant_scope",
  "tenant_scoped_idempotency_key",
  "sql_has_tenant_or_owner_filter",
  "rag_citation_ids_validated",
  "rag_retrieved_context_is_untrusted",
  "jwt_audience_issuer_validated",
  "event_version_monotonic_guard",
  "pagination_uses_stable_tiebreaker",
  "async_update_atomicity_guard",
  "react_uses_functional_state_update",
  "graphql_uses_batching_or_dataloader",
];

export default function ValidatorsPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Structural Validators" description="Repair-property checks that supplement regression tests." />
      <DocsLayout>
        <h1>Validator registry</h1>
        <p>Each case declares required validators by name. The registry receives the patched workspace, changed files, finding, and case metadata, then returns evidence-backed pass or fail results.</p>
        <h2>Configured checks</h2>
        <ul>{validators.map((validator) => <li key={validator}><code>{validator}</code></li>)}</ul>
        <h2>Tolerant validation</h2>
        <p>Validators accept multiple credible repair patterns, such as dependency-based or explicit admin authorization checks. They are deliberately not exact matches for mock patches.</p>
      </DocsLayout>
    </>
  );
}
