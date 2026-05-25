import Link from "next/link";
import type { ReactNode } from "react";

const pages = [
  ["Getting Started", "/docs/getting-started"],
  ["Metrics", "/docs/metrics"],
  ["Patch Validation", "/docs/patch-validation"],
  ["Structural Validators", "/docs/validators"],
  ["Adding Cases", "/docs/adding-cases"],
  ["Adding Reviewers", "/docs/adding-reviewers"],
  ["GitHub Action", "/docs/github-action"],
];

export function DocsLayout({ children }: { children: ReactNode }) {
  return (
    <div className="docs-layout">
      <aside className="panel docs-nav">
        <strong>Documentation</strong>
        {pages.map(([label, href]) => <Link href={href} key={href}>{label}</Link>)}
      </aside>
      <article className="panel prose">{children}</article>
    </div>
  );
}
