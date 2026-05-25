export function DiffViewer({ diff }: { diff: string }) {
  return <pre className="diff">{diff}</pre>;
}
