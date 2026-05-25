import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "../components/AppShell";

export const metadata: Metadata = {
  title: "CodeReview Arena",
  description: "Local, execution-backed audits for AI code reviewers (code-review-arena).",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
