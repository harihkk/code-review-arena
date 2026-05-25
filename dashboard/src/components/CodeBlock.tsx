export function CodeBlock({ children, compact = false }: { children: string; compact?: boolean }) {
  return <pre className={compact ? "mono-output" : "diff"}>{children || "No output captured."}</pre>;
}
