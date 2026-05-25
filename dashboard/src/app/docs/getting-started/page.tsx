import { CodeBlock } from "../../../components/CodeBlock";
import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const commands = `python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
arena validate benchmark_sets/v1
arena run benchmark_sets/v1 --reviewer mock:perfect_patch --mode full --allow-local-execution
arena leaderboard runs/ --metric validated_f_beta --beta 1.0
arena serve`;

export default function GettingStartedPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="Getting Started" description="Run a deterministic benchmark locally without provider credentials." />
      <DocsLayout>
        <h1>Getting Started</h1>
        <p>The mock patch reviewer is deterministic and exercises patch application, tests, validators, reports, storage, and the API without paid model calls.</p>
        <CodeBlock compact>{commands}</CodeBlock>
        <h2>Safe execution</h2>
        <p>Local test execution is disabled by default. Pass <code>--allow-local-execution</code> only for benchmark fixtures you trust; configured Docker execution is preferred for stronger isolation.</p>
      </DocsLayout>
    </>
  );
}
