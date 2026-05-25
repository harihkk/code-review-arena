import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const metrics = [
  ["detection_precision", "Localized seeded detections divided by localized detections plus unmatched findings."],
  ["detection_recall", "Seeded cases correctly detected and localized divided by all cases."],
  ["detection_f_beta", "The weighted harmonic mean for detection only. It does not indicate a working repair."],
  ["validated_precision", "Deterministically passing cases divided by passing cases plus unmatched findings."],
  ["validated_recall", "Deterministically passing cases divided by all seeded cases."],
  ["validated_f_beta", "The primary full-mode metric: found, localized, and passed required patch validation."],
  ["deterministic_pass_rate", "Fraction of cases with a complete deterministic pass."],
  ["patch_apply_rate", "Cleanly applied patches divided by provided patches."],
  ["structural_pass_rate", "Passed validators divided by validators run."],
  ["test_pass_rate", "Passed required test executions divided by tests run."],
  ["false_positives_per_case", "Unmatched findings divided by case count."],
  ["cost_per_validated_fix", "Estimated total reviewer cost divided by deterministic passes."],
];

export default function MetricsPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Metrics" description="Detection and validation are reported separately by design." />
      <DocsLayout>
        <h1>Detection is not validation</h1>
        <div className="definition-callout">
          <p><code>detection_f_beta</code> = found and localized the seeded bug.</p>
          <p><code>validated_f_beta</code> = found and localized the bug and passed deterministic validation.</p>
        </div>
        <dl className="metric-definitions">
          {metrics.map(([name, definition]) => (
            <div key={name}><dt><code>{name}</code></dt><dd>{definition}</dd></div>
          ))}
        </dl>
        <p>Beta controls precision versus recall weighting: <code>0.5</code> favors precision, <code>1.0</code> balances them, and <code>2.0</code> favors recall.</p>
      </DocsLayout>
    </>
  );
}
