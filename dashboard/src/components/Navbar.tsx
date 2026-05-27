import Link from "next/link";

const links = [
  { href: "/", label: "Overview" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/cases", label: "Cases" },
  { href: "/reports/audit-v1", label: "Audit Pack v1" },
  { href: "/methodology", label: "Methodology" },
  { href: "/docs", label: "Docs" },
  { href: "/runs", label: "Runs" },
];

export function Navbar() {
  return (
    <header className="topbar">
      <Link className="brand" href="/">Code Review Arena</Link>
      <nav className="nav" aria-label="Primary">
        {links.map((link) => (
          <Link href={link.href} key={link.href}>{link.label}</Link>
        ))}
      </nav>
    </header>
  );
}
