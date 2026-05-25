import Link from "next/link";
import { PageHeader } from "../components/PageHeader";

const features = [
  {
    title: "Seeded Production Bugs",
    copy: "Realistic PRs across FastAPI, Spring Boot, GraphQL, React, Kafka, Redis, SQL, RAG, async, and API compatibility.",
  },
  {
    title: "Patch Validation",
    copy: "Suggested patches are applied to isolated workspaces and checked through tests and structural validators.",
  },
  {
    title: "Noise-Aware Metrics",
    copy: "Compare detection_f_beta, validated_f_beta, false positives, patch apply rate, and cost per validated fix.",
  },
];

const pipeline = ["Seeded PR", "AI reviewer", "JSON findings", "Suggested patch", "Apply patch", "Run tests", "Run validators", "Score outcome"];

export default function Home() {
  return (
    <>
      <section className="hero">
        <PageHeader
          eyebrow="Deterministic benchmark"
          title="CodeReview Arena"
          description="Local, execution-backed audits for AI code reviewers."
          actions={<div className="hero-actions"><Link className="button primary" href="/leaderboard">View Leaderboard</Link><Link className="button" href="/methodology">Read Methodology</Link></div>}
        />
        <p className="hero-copy">
          CodeReview Arena tests whether AI reviewers can catch seeded production bugs, generate patches,
          apply them cleanly, pass regression tests, and satisfy structural validators - not just write plausible comments.
        </p>
      </section>
      <section className="feature-grid">
        {features.map((feature) => (
          <article className="panel feature" key={feature.title}>
            <h2>{feature.title}</h2>
            <p>{feature.copy}</p>
          </article>
        ))}
      </section>
      <section className="panel pipeline-panel">
        <h2>Validation Pipeline</h2>
        <div className="pipeline">
          {pipeline.map((step, index) => (
            <div className="pipeline-node" key={step}>
              <span>{step}</span>
              {index < pipeline.length - 1 && <b aria-hidden="true">-&gt;</b>}
            </div>
          ))}
        </div>
      </section>
      <section className="panel thesis">
        <p className="eyebrow">Core principle</p>
        <h2>Detection is not validation.</h2>
        <p>
          A model can correctly describe a bug and still produce no usable fix. CodeReview Arena reports both
          <code>detection_f_beta</code> and <code>validated_f_beta</code> so those failures are visible.
        </p>
      </section>
    </>
  );
}
