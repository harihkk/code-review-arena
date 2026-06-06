import type { CaseResult } from "../lib/api";

export function ValidationFunnel({ cases }: { cases: CaseResult[] }) {
  const stages = [
    ["Cases", cases.length],
    ["Detected", cases.filter((item) => item.bug_found).length],
    ["Localized", cases.filter((item) => item.correct_file && item.correct_line).length],
    ["Patches provided", cases.filter((item) => item.patch_provided).length],
    ["Patches applied", cases.filter((item) => item.patch_applied).length],
    ["Tests passed", cases.filter((item) => item.tests_passed === true).length],
    ["Validators passed", cases.filter((item) => item.validators_passed === true).length],
    ["Deterministic passes", cases.filter((item) => item.deterministic_pass === true).length],
  ] as const;
  return (
    <table className="data-table funnel-table">
      <thead>
        <tr><th>Stage</th><th className="numeric">Count</th><th className="numeric">Percent</th></tr>
      </thead>
      <tbody>
        {stages.map(([label, value]) => (
          <tr key={label}>
            <td>{label}</td>
            <td className="numeric strong-metric">{value}</td>
            <td className="numeric">{cases.length ? `${Math.round((value / cases.length) * 100)}%` : "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
