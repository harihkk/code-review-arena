import { PageHeader } from "../../components/PageHeader";
import {
  CONTROL_BASELINE_NOTE,
  reviewerDisplayName,
} from "../../lib/reviewers";

const flow = [
  "Reviewer output",
  "Suggested patch",
  "Isolated workspace",
  "Tests",
  "Validators",
  "Metrics",
];
const sections = [
  [
    "1. What is measured",
    "A run records detection, localization, patch availability, patch application, tests, structural validation, false positives, cost, and latency.",
  ],
  [
    "2. Detection vs validation",
    "Detection measures whether the seeded bug was found and localized. Validation measures whether the associated fix completed deterministic checks.",
  ],
  [
    "3. Case design",
    "Cases are seeded pull-request fixtures with known failure behavior, expected files, execution requirements, and validation criteria.",
  ],
  [
    "4. Reviewer-visible context",
    "Reviewer inputs include the pull-request diff and relevant files. Ground truth, validators, and reference patches are not sent to the reviewer.",
  ],
  [
    "5. Patch application",
    "Suggested unified diffs are applied to copied run workspaces. A patch that cannot apply cleanly fails the validation path.",
  ],
  [
    "6. Test execution",
    "Cases can require fixture-owned regression tests after patch application. Local execution is explicit and opt-in.",
  ],
  [
    "7. Structural validators",
    "Validators check repair properties such as tenant scoping, idempotency, event ordering, citation grounding, and API contract behavior.",
  ],
  [
    "8. Metrics",
    "The primary full-mode ranking metric is validated_f_beta. Supporting metrics expose detection, patch apply, test pass, validator pass, false positives, cost, and latency.",
  ],
  [
    "9. Baselines",
    "Deterministic controls exercise known success paths, detection-only behavior, malformed patches, missing patches, and custom command integration.",
  ],
  [
    "10. Limitations",
    "The benchmark is curated and small. Validators are hand-authored. Tests do not prove all correctness. Valid fixes may fail if validators are narrow.",
  ],
];
const baselines: { reviewer: string; model?: string; purpose: string }[] = [
  {
    reviewer: "reference-patch",
    purpose: "Reads committed known-good reference.patch files.",
  },
  {
    reviewer: "mock",
    model: "perfect_patch",
    purpose: "Harness success control.",
  },
  {
    reviewer: "mock",
    model: "keyword_gamer",
    purpose: "Detects bugs but does not produce validated fixes.",
  },
  {
    reviewer: "mock",
    model: "bad_patch",
    purpose: "Detects bugs while supplying failing fixes.",
  },
  {
    reviewer: "mock",
    model: "detects_no_patch",
    purpose: "Detects bugs without patch output.",
  },
  {
    reviewer: "mock",
    model: "malformed_patch",
    purpose: "Returns invalid patch output.",
  },
  {
    reviewer: "custom-command",
    purpose:
      "Runs an external reviewer command through structured input and output.",
  },
];

export default function MethodologyPage() {
  return (
    <>
      <PageHeader
        eyebrow="Methodology"
        title="Methodology"
        description="How Code Review Arena turns reviewer output into reproducible validation evidence."
      />
      <section className="panel method-pipeline">
        <h2>Evaluation flow</h2>
        <div className="pipeline">
          {flow.map((step, index) => (
            <div className="pipeline-node" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </section>
      <div className="method-grid">
        {sections.map(([title, copy]) => (
          <section className="panel method-section" key={title}>
            <h2>{title}</h2>
            <p>{copy}</p>
          </section>
        ))}
      </div>
      <section className="panel section-space">
        <h2>Baseline controls</h2>
        <p className="section-caption">{CONTROL_BASELINE_NOTE}</p>
        <table className="data-table">
          <thead>
            <tr>
              <th>Reviewer</th>
              <th>Purpose</th>
            </tr>
          </thead>
          <tbody>
            {baselines.map((item) => (
              <tr key={`${item.reviewer}:${item.model ?? ""}`}>
                <td>
                  <span className="reviewer-name">
                    <strong>{reviewerDisplayName(item)}</strong>
                  </span>
                </td>
                <td>{item.purpose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel callout section-space">
        <p>
          Code Review Arena is a local audit harness, not a large-scale public
          ranking. Large public benchmarks evaluate different things, often at
          broader scale. This project focuses on local execution-backed
          validation of patch outputs.
        </p>
      </section>
    </>
  );
}
