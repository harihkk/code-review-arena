import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

export default function AuditPackV2Page() {
  return (
    <>
      <PageHeader
        eyebrow="Docs"
        title="Audit Pack v2"
        description="A second batch of certified, leak-free cases targeting high-impact logic defects."
      />
      <DocsLayout>
        <h1>Audit Pack v2</h1>
        <p>
          Audit Pack v2 is a 10-case pack that targets small but high-impact logic defects: the
          kind that pass a casual read yet change behavior in production. Every case is authored
          leak-free (no ground-truth vocabulary in the diff, comments, or test names) and fully
          certified (the buggy baseline fails, the reference fix passes, and the tests kill every
          viable mutant).
        </p>
        <h2>Cases</h2>
        <ul>
          <li><code>money_discount_rounding_001</code>: per-unit reduction loses money on multi-unit orders</li>
          <li><code>ratelimit_window_boundary_001</code>: fixed-window limiter admits one past the cap</li>
          <li><code>permission_precedence_001</code>: boolean precedence bypasses a guard</li>
          <li><code>overdraft_min_balance_001</code>: lowest-balance tracker compares the wrong way</li>
          <li><code>progress_zero_division_001</code>: completion percentage divides by zero</li>
          <li><code>page_count_ceil_001</code>: page count floors and drops the last page</li>
          <li><code>truthiness_default_001</code>: fallback discards an explicit zero</li>
          <li><code>preview_truncation_001</code>: preview truncates one character short</li>
          <li><code>retry_backoff_cap_001</code>: backoff delay grows without bound</li>
          <li><code>eligibility_and_or_001</code>: check uses or where both conditions are required</li>
        </ul>
        <h2>Adversarial baseline</h2>
        <p>
          <code>shallow-patch</code> is a generic adversarial reviewer that works on any pack: it
          localizes the bug from the reference patch, then proposes a no-op change that applies
          cleanly but repairs nothing. It scores detection near 1.0 with{" "}
          <code>validated_case_rate</code> 0.0, the detection-versus-validation gap the harness
          exists to measure.
        </p>
        <h2>Commands</h2>
        <pre className="code-block">{`arena validate benchmark_sets/audit_v2
arena lint-cases benchmark_sets/audit_v2 --strict
arena certify-pack benchmark_sets/audit_v2 --allow-local-execution --strict certified
arena run benchmark_sets/audit_v2 --reviewer reference-patch --mode full --allow-local-execution
arena run benchmark_sets/audit_v2 --reviewer shallow-patch --mode full --allow-local-execution`}</pre>
        <h2>Results</h2>
        <p>
          The rendered report for this pack lives at{" "}
          <a href="/reports/audit-v2">/reports/audit-v2</a>: the verified reference patch against
          the generic adversarial baseline.
        </p>
        <h2>Primary metric</h2>
        <p>
          Use <code>validated_case_rate</code> in full mode. Detection metrics alone do not prove a
          working repair.
        </p>
      </DocsLayout>
    </>
  );
}
