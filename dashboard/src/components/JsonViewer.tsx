import { CodeBlock } from "./CodeBlock";

export function JsonViewer({ value }: { value: unknown }) {
  return <CodeBlock compact>{JSON.stringify(value, null, 2)}</CodeBlock>;
}
