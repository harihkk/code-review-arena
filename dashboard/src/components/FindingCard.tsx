import { Finding } from "../lib/api";

export function FindingCard({ finding, truePositive, reason }: { finding: Finding; truePositive: boolean; reason: string | null }) {
  return (
    <article className={`finding ${truePositive ? "true" : "false"}`}>
      <div className="finding-meta">
        <strong>{finding.title}</strong>
        <span className={`badge ${truePositive ? "success" : "danger"}`}>
          {truePositive ? "Matched bug" : reason ?? "Unmatched"}
        </span>
      </div>
      <p>{finding.summary}</p>
      <div className="file">{finding.file}:{finding.line_start}-{finding.line_end} | {finding.severity} | confidence {finding.confidence.toFixed(2)}</div>
      <p className="fix"><strong>Suggested fix:</strong> {finding.suggested_fix ?? "No natural-language fix supplied."}</p>
    </article>
  );
}
