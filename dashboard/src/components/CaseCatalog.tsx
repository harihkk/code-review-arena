"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { CaseSummary } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

export function CaseCatalog({ cases }: { cases: CaseSummary[] }) {
  const [pack, setPack] = useState<"v1" | "audit_v1">("audit_v1");
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [stack, setStack] = useState("");
  const packCases = cases.filter((item) => item.benchmark_set === pack);
  const categories = Array.from(new Set(packCases.map((item) => item.category))).sort();
  const stacks = Array.from(new Set(packCases.flatMap((item) => item.stack))).sort();
  const visible = useMemo(() => cases.filter((item) =>
    item.benchmark_set === pack &&
    (!category || item.category === category) &&
    (!severity || item.severity === severity) &&
    (!stack || item.stack.includes(stack))
  ), [cases, pack, category, severity, stack]);
  return (
    <>
      <div className="controls panel case-filters">
        <label>Pack<select value={pack} onChange={(event) => {
          setPack(event.target.value as "v1" | "audit_v1");
          setCategory("");
          setStack("");
        }}><option value="audit_v1">audit_v1</option><option value="v1">v1</option></select></label>
        <label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All</option>{categories.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
        <label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="">All</option><option>high</option><option>medium</option><option>low</option></select></label>
        <label>Stack<select value={stack} onChange={(event) => setStack(event.target.value)}><option value="">All</option>{stacks.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr><th>Case</th><th>Pack</th><th>Category</th><th>Severity</th><th>Stack</th><th>Patch required</th><th>Tests</th><th>Validators</th></tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={`${item.benchmark_set}-${item.id}`}>
                <td><Link href={`/cases/${item.id}?benchmark_set=${item.benchmark_set}`}><strong>{item.id}</strong></Link><div className="table-subtitle">{item.title}</div></td>
                <td><code>{item.benchmark_set}</code></td>
                <td>{item.category}</td>
                <td><StatusBadge tone={item.severity === "high" ? "danger" : "warning"}>{item.severity}</StatusBadge></td>
                <td><div className="stack">{item.stack.map((tag) => <StatusBadge tone="neutral" key={tag}>{tag}</StatusBadge>)}</div></td>
                <td>{item.validation.patch_required ? "yes" : "no"}</td>
                <td>{item.execution.run_tests ? "configured" : "not configured"}</td>
                <td>{item.validation.structural_validators.length || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
