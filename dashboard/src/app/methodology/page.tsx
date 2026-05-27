import { PageHeader } from "../../components/PageHeader";

const steps = [
  "Seeded PR",
  "Reviewer",
  "Structured finding",
  "Suggested patch",
  "Apply patch",
  "Run tests",
  "Run validators",
  "Compute metrics",
];

const sections = [
  ["1. What is measured", "Code Review Arena records whether a reviewer identifies a seeded bug, localizes it, supplies a patch, and produces an execution-backed outcome."],
  ["2. Detection vs validation", "detection_f_beta measures found and localized bugs. validated_f_beta measures detected bugs whose fixes pass required deterministic validation."],
  ["3. Benchmark case design", "Cases are small pull-request fixtures with known failure behavior, ground truth, validation requirements, and regression evidence."],
  ["4. Patch application", "Suggested unified diffs are applied to isolated copied workspaces. A patch that cannot apply cannot receive a validated outcome."],
  ["5. Test execution", "Cases can require fixture-owned regression tests after patch application. Local execution is explicit and opt-in."],
  ["6. Structural validators", "Hand-authored validators check repair properties that tests may not fully express, such as tenant scoping or event ordering guards."],
  ["7. Baselines", "reference-patch and mock reviewers are deterministic controls used to exercise success and failure paths. They are not external model comparisons."],
  ["8. Metrics", "The primary full-mode ranking metric is validated_f_beta. Reports also expose patch apply, test, structural pass, false-positive, cost, and latency measures."],
  ["9. Limitations", "The audit pack is curated and small. Validators can be too narrow, and passing tests cannot establish every production property."],
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
        <h2>Evaluation pipeline</h2>
        <div className="pipeline">
          {steps.map((step, index) => (
            <div className="pipeline-step" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              {step}
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
      <section className="panel callout section-space">
        <p>
          Code Review Arena is a local audit harness. It is not a large-scale public adoption benchmark.
          Large public benchmarks evaluate different things, often at broader scale. Code Review Arena
          focuses on local execution-backed validation of patch outputs.
        </p>
      </section>
    </>
  );
}
