"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const pages = [
  ["Getting Started", "/docs/getting-started"],
  ["Metrics", "/docs/metrics"],
  ["Audit Pack v1", "/docs/audit-pack-v1"],
  ["Audit Pack v2", "/docs/audit-pack-v2"],
  ["Reference Patches", "/docs/reference-patches"],
  ["Custom Command Reviewer", "/docs/custom-command-reviewer"],
  ["Validators", "/docs/validators"],
  ["Audit Report", "/docs/audit-report"],
  ["CLI Reference", "/docs/cli-reference"],
  ["Troubleshooting", "/docs/troubleshooting"],
];

export function DocsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="docs-layout">
      <aside className="panel docs-nav">
        <Link className={`docs-home ${pathname === "/docs" ? "active" : ""}`} href="/docs">Documentation</Link>
        {pages.map(([label, href]) => <Link className={pathname === href ? "active" : undefined} href={href} key={href}>{label}</Link>)}
      </aside>
      <article className="panel prose">{children}</article>
    </div>
  );
}
