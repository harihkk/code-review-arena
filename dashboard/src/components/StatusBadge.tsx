export type BadgeTone = "success" | "warning" | "danger" | "neutral";

export function StatusBadge({ tone, children }: { tone: BadgeTone; children: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
