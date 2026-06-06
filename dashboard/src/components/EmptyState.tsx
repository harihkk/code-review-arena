import { CodeBlock } from "./CodeBlock";

export function EmptyState({
  title = "No data found",
  message,
  command,
}: {
  title?: string;
  message: string;
  command?: string;
}) {
  return (
    <section className="panel empty">
      <h2>{title}</h2>
      <p>{message}</p>
      {command ? <CodeBlock compact label="Next command">{command}</CodeBlock> : null}
    </section>
  );
}
