import Link from "next/link";

const links = [
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/runs", label: "Runs" },
  { href: "/cases", label: "Cases" },
  { href: "/methodology", label: "Methodology" },
  { href: "/reports/audit-v1", label: "Audit Report" },
  { href: "/docs", label: "Docs" },
];

export function Navbar() {
  return (
    <header className="topbar">
      <div>
        <Link className="brand" href="/">CodeReview Arena</Link>
        <p className="tagline">
          Local, execution-backed audits for AI code reviewers. Repo: code-review-arena
        </p>
      </div>
      <nav className="nav" aria-label="Primary">
        {links.map((link) => (
          <Link href={link.href} key={link.href}>{link.label}</Link>
        ))}
      </nav>
    </header>
  );
}
