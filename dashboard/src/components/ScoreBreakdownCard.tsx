import { Breakdown } from "../lib/api";

export function ScoreBreakdownCard({ breakdown }: { breakdown: Breakdown }) {
  const entries = [
    ["Concept", breakdown.concept_match, 35],
    ["File", breakdown.file_match, 20],
    ["Line overlap", breakdown.line_overlap, 15],
    ["Severity", breakdown.severity_match, 10],
    ["Fix quality", breakdown.fix_quality, 15],
    ["Precision", breakdown.no_false_positives, 5],
  ];
  return (
    <section className="panel">
      <h3>Scoring breakdown <span className="badge success">{breakdown.total.toFixed(1)}/100</span></h3>
      <div className="score-grid">
        {entries.map(([label, value, total]) => (
          <div className="score-item" key={String(label)}>
            <span>{label}</span><strong>{Number(value).toFixed(1)}/{total}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}
