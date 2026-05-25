"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { CaseSummary } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

export function CaseCatalog({ cases }: { cases: CaseSummary[] }) {
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState("");
  const [stack, setStack] = useState("");
  const [tests, setTests] = useState(false);
  const [validators, setValidators] = useState(false);
  const categories = Array.from(new Set(cases.map((item) => item.category))).sort();
  const stacks = Array.from(new Set(cases.flatMap((item) => item.stack))).sort();
  const visible = useMemo(() => cases.filter((item) =>
    (!category || item.category === category) &&
    (!severity || item.severity === severity) &&
    (!stack || item.stack.includes(stack)) &&
    (!tests || item.execution.run_tests) &&
    (!validators || item.validation.structural_validators.length > 0)
  ), [cases, category, severity, stack, tests, validators]);
  return (
    <>
      <div className="controls panel case-filters">
        <label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All</option>{categories.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
        <label>Severity<select value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="">All</option><option>high</option><option>medium</option><option>low</option></select></label>
        <label>Stack<select value={stack} onChange={(event) => setStack(event.target.value)}><option value="">All</option>{stacks.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
        <label className="checkbox"><input type="checkbox" checked={tests} onChange={(event) => setTests(event.target.checked)} /> Has tests</label>
        <label className="checkbox"><input type="checkbox" checked={validators} onChange={(event) => setValidators(event.target.checked)} /> Has validators</label>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr><th>Case</th><th>Category</th><th>Severity</th><th>Stack</th><th>Seeded Bug</th><th>Validation</th></tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td><Link href={`/cases/${item.id}`}><strong>{item.id}</strong></Link><div className="table-subtitle">{item.title}</div></td>
                <td>{item.category}</td>
                <td><StatusBadge tone={item.severity === "high" ? "danger" : "warning"}>{item.severity}</StatusBadge></td>
                <td><div className="stack">{item.stack.map((tag) => <StatusBadge tone="neutral" key={tag}>{tag}</StatusBadge>)}</div></td>
                <td>{item.ground_truth_summary}</td>
                <td><div className="stack">{item.validation.patch_required && <StatusBadge tone="neutral">Patch required</StatusBadge>}{item.execution.run_tests && <StatusBadge tone="neutral">Tests</StatusBadge>}{item.validation.structural_validators.length > 0 && <StatusBadge tone="neutral">Validators</StatusBadge>}</div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
