type GapRow = {
  reviewer: string;
  model: string;
  detection_f_beta: number | null;
  validated_f_beta: number | null;
};

export function GapTable({ rows }: { rows: GapRow[] }) {
  return (
    <div className="gap-bars">
      {rows.map((row) => {
        const detection = row.detection_f_beta ?? 0;
        const validated = row.validated_f_beta ?? 0;
        const gap = Math.max(0, detection - validated);
        const label = row.model ? `${row.reviewer}:${row.model}` : row.reviewer;
        return (
          <div className="gap-row" key={label}>
            <span className="gap-label">{label}</span>
            <div className="gap-track" title={`Detection ${detection.toFixed(3)} / validated ${validated.toFixed(3)}`}>
              <span className="gap-detection" style={{ width: `${detection * 100}%` }} />
              <span className="gap-validation" style={{ width: `${validated * 100}%` }} />
            </div>
            <span className="gap-value">{gap.toFixed(3)}</span>
          </div>
        );
      })}
    </div>
  );
}
