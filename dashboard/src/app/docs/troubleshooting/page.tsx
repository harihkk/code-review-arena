import { CodeBlock } from "../../../components/CodeBlock";
import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const install = `python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"`;

export default function TroubleshootingPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Troubleshooting" description="Common local setup, evidence-generation, and dashboard recovery steps." />
      <DocsLayout>
        <h1>Troubleshooting</h1>
        <h2><code>arena</code> command not found or <code>pytest</code> not found</h2>
        <p>Create and activate the development environment, then install the editable package:</p>
        <CodeBlock compact>{install}</CodeBlock>
        <h2>Virtual environment not activated</h2>
        <p>Run <code>source .venv/bin/activate</code>. Confirm with <code>which arena</code> before running an audit.</p>
        <h2>npm dependencies missing</h2>
        <CodeBlock compact>{`cd dashboard
npm install
npm run build`}</CodeBlock>
        <h2>Stale Docker containers</h2>
        <p>Stop existing services with <code>docker compose down</code>, then start a fresh local stack with <code>docker compose up --build</code>.</p>
        <h2>API healthy but dashboard stale</h2>
        <p>Restart the Next.js development server and regenerate report or verification JSON when inspecting static audit pages.</p>
        <h2>Audit report missing</h2>
        <CodeBlock compact>{`arena run benchmark_sets/audit_v1 --reviewer reference-patch --mode full --allow-local-execution
arena audit-report runs/ --output docs/reports/audit-v1-results.md`}</CodeBlock>
        <h2>No runs shown</h2>
        <p>The API-backed pages require saved runs in the configured database. Generate a run, start <code>arena serve</code>, and reload the page. Static report and verification pages read their generated JSON snapshots.</p>
      </DocsLayout>
    </>
  );
}
