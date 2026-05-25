export function MissedBugList({ cases }: { cases: string[] }) {
  return cases.length ? <ul className="list">{cases.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="subtitle">No seeded bugs missed.</p>;
}
