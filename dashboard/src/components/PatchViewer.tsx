import { CodeBlock } from "./CodeBlock";

export function PatchViewer({ patch }: { patch: string | null }) {
  return patch ? <CodeBlock>{patch}</CodeBlock> : <p className="empty-inline">No patch supplied.</p>;
}
