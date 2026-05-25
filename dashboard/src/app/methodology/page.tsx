import { PageHeader } from "../../components/PageHeader";

const sections = [
  ["What CodeReview Arena measures", "A local benchmark run begins with intentionally buggy pull requests and records localization, patches, execution outcomes, validator evidence, false positives, cost, and latency."],
  ["Detection vs validation", "Detection means a reviewer found and localized the seeded defect. Validation means that result also produced an acceptable patch outcome: clean application, required passing tests, required validator passes, and acceptable precision."],
  ["Patch application pipeline", "Each suggested unified diff is applied to an isolated run workspace copied from the buggy after snapshot. Benchmark fixtures are never mutated."],
  ["Test execution", "Cases may execute regression tests inside the copied workspace. Local execution is opt-in; Docker can be configured for stronger containment."],
  ["Structural validators", "Validators check repair properties such as admin authorization, tenant scoping, idempotency guards, or citation validation. They accept multiple credible code patterns rather than one mock-patch shape."],
  ["False-positive fatigue", "Unmatched findings count against precision and can prevent deterministic passage. A reviewer that floods a PR with unsupported warnings is not treated as effective."],
  ["Cost and latency", "Reports track estimated cost per validated fix and elapsed latency per case so repair quality can be compared against operational cost."],
  ["Intended use", "Arena is designed for reproducible local audits, private reviewer evaluation, prompt or model comparisons, and failure-mode testing before deployment."],
];

export default function MethodologyPage() {
  return (
    <>
      <PageHeader eyebrow="Methodology" title="Outcome-based evaluation" description="How deterministic patch validation builds evidence beyond plausible review comments." />
      <div className="prose panel methodology">
        {sections.map(([title, copy]) => <section key={title}><h2>{title}</h2><p>{copy}</p></section>)}
        <section>
          <h2>Limitations</h2>
          <ul>
            <li>Version 1 is a small curated benchmark set, not a scale benchmark.</li>
            <li>Structural validators are hand-authored and may still reject some valid repairs.</li>
            <li>Passing tests provides useful evidence but cannot prove complete correctness.</li>
            <li>Arena is intended for local reproducibility and audit workflows, not claims of universal model quality.</li>
          </ul>
        </section>
      </div>
    </>
  );
}
