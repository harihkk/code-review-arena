import { CodeBlock } from "../../../components/CodeBlock";
import { DocsLayout } from "../../../components/DocsLayout";
import { PageHeader } from "../../../components/PageHeader";

const workflow = `- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: python -m pip install -e ".[dev]"
- run: arena validate benchmark_sets/v1
- run: arena run benchmark_sets/v1 --reviewer control:perfect_patch --mode full --allow-local-execution
- run: arena leaderboard runs/ --metric validated_case_rate --beta 1.0 --include-unverified
- uses: actions/upload-artifact@v4
  with:
    name: arena-runs
    path: runs/`;

export default function GithubActionPage() {
  return (
    <>
      <PageHeader eyebrow="Docs" title="GitHub Action Audit Mode" description="Preserve reproducible deterministic reports in CI." />
      <DocsLayout>
        <h1>Benchmark workflow</h1>
        <p>The included manual-friendly workflow validates the benchmark and runs a key-free deterministic reviewer. Teams can adapt the same harness for internal reviewers without treating this as proof of broad production adoption.</p>
        <CodeBlock compact>{workflow}</CodeBlock>
        <p>Paid hosted reviewers should be invoked deliberately with repository secrets and should not be scheduled automatically for every change.</p>
      </DocsLayout>
    </>
  );
}
