import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "../components/AppShell";

export const metadata: Metadata = {
  title: "Code Review Arena",
  description: "Execution-backed benchmark for AI code-review agents.",
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
