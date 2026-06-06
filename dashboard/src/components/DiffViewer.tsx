import { CodeBlock } from "./CodeBlock";

export function DiffViewer({ diff }: { diff: string }) {
  return <CodeBlock label="Diff">{diff}</CodeBlock>;
}
