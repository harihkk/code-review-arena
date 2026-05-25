import type { ReactNode } from "react";
import { Navbar } from "./Navbar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <main className="shell">
      <Navbar />
      {children}
    </main>
  );
}
