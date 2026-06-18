import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

export default function AuditPackV1Page() {
  return (
    <>
      <PageHeader
        eyebrow="Docs"
        title="Audit Pack v1"
        description="Harder patch-backed failures for security, distributed systems, RAG, concurrency, and idempotency."
      />
      <DocsLayout>
        <h1>Audit Pack v1</h1>
        <p>
          Audit Pack v1 is a curated 10-case pack for reviewers that must localize a defect,
          supply a patch, pass regression tests, and satisfy structural validators. Cases span
          security, distributed systems, RAG safety, concurrency, idempotency, API correctness,
          and pagination.
        </p>
        <h2>Cases</h2>
        <ul>
          <li><code>security_fastapi_multitenant_admin_bypass_001</code>: tenant admin authorization</li>
          <li><code>distributed_kafka_duplicate_event_001</code>: Kafka duplicate delivery</li>
          <li><code>rag_fabricated_citation_001</code>: RAG citation grounding</li>
          <li><code>async_balance_race_001</code>: async lost updates</li>
          <li><code>idempotency_key_tenant_scope_001</code>: tenant-scoped idempotency</li>
          <li><code>security_sql_join_ownership_leak_001</code>: SQL ownership leak</li>
          <li><code>security_jwt_audience_validation_001</code>: JWT audience and issuer checks</li>
          <li><code>distributed_out_of_order_event_001</code>: out-of-order events</li>
          <li><code>api_pagination_cursor_skip_001</code>: pagination cursor tiebreaker</li>
          <li><code>rag_prompt_injection_policy_override_001</code>: RAG prompt injection</li>
        </ul>
        <h2>Reference patches</h2>
        <p>
          Each case ships <code>reference.patch</code>. Run{" "}
          <code>arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution</code>{" "}
          to validate the static artifacts.
        </p>
        <h2>Commands</h2>
        <pre className="code-block">{`arena validate benchmark_sets/audit_v1
arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena run benchmark_sets/audit_v1 --reviewer mock:perfect_patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_case_rate --beta 1.0
arena audit-report runs/ --output docs/reports/audit-v1-results.md`}</pre>
        <h2>Primary metric</h2>
        <p>
          Use <code>validated_case_rate</code> in full mode. Detection metrics alone do not prove a
          working repair.
        </p>
      </DocsLayout>
    </>
  );
}
