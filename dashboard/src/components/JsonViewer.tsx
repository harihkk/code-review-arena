import { CodeBlock } from "./CodeBlock";

export function JsonViewer({ value }: { value: unknown }) {
  return <CodeBlock compact label="JSON">{JSON.stringify(value, null, 2)}</CodeBlock>;
}
