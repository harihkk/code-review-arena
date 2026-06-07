import { shortFailureLabel } from "./FailureReasonList";

export function FailureReasonChart({
  counts,
}: {
  counts: Record<string, number>;
}) {
  const entries = Object.entries(counts).sort(
    (left, right) => right[1] - left[1],
  );
  const max = Math.max(1, ...entries.map(([, count]) => count));
  if (!entries.length)
    return <p className="pass-text">No failure reasons recorded.</p>;
  return (
    <div className="failure-chart">
      {entries.map(([reason, count]) => (
        <div className="failure-bar-row" key={reason}>
          <div className="failure-bar-label">
            <span>{shortFailureLabel(reason)}</span>
            <span>{count}</span>
          </div>
          <div className="failure-bar">
            <span style={{ width: `${(count / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
