"use client";

import { useState } from "react";

export function CodeBlock({
  children,
  compact = false,
  label,
}: {
  children: string;
  compact?: boolean;
  label?: string;
}) {
  const [copied, setCopied] = useState(false);
  const value = children || "No output captured.";

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1200);
  }

  return (
    <figure className={`code-frame ${compact ? "compact" : ""}`}>
      <figcaption>
        <span>{label ?? "Code"}</span>
        <button type="button" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
      </figcaption>
      <pre className={compact ? "mono-output" : "diff"}>{value}</pre>
    </figure>
  );
}
