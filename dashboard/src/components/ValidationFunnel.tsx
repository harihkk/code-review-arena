import type { CaseResult } from "../lib/api";

export function ValidationFunnel({ cases }: { cases: CaseResult[] }) {
  const stages = [
    ["Total cases", cases.length],
    ["Bugs detected", cases.filter((item) => item.bug_found).length],
    ["Localized", cases.filter((item) => item.correct_file && item.correct_line).length],
    ["Patches provided", cases.filter((item) => item.patch_provided).length],
    ["Patches applied", cases.filter((item) => item.patch_applied).length],
    ["Tests passed", cases.filter((item) => item.tests_passed === true).length],
    ["Validators passed", cases.filter((item) => item.validators_passed === true).length],
    ["Deterministic passes", cases.filter((item) => item.deterministic_pass === true).length],
  ] as const;
  return (
    <div className="funnel">
      {stages.map(([label, value]) => (
        <div className="funnel-step" key={label}>
          <strong>{value}</strong>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}
