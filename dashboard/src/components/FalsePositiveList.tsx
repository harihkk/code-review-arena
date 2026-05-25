export function FalsePositiveList({ findings }: { findings: string[] }) {
  return findings.length ? <ul className="list">{findings.map((finding) => <li key={finding}>{finding}</li>)}</ul> : <p className="subtitle">No false positives.</p>;
}
