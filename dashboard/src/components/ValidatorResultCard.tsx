import { StatusBadge } from "./StatusBadge";

export type ValidatorView = {
  name: string;
  passed: boolean;
  confidence: number;
  message: string;
  evidence: string[];
  error: string | null;
};

export function ValidatorResultCard({ result }: { result: ValidatorView }) {
  return (
    <article className="validator-card">
      <div className="row-between">
        <strong>{result.name}</strong>
        <StatusBadge tone={result.passed ? "success" : "danger"}>
          {result.passed ? "Passed" : "Failed"}
        </StatusBadge>
      </div>
      <p>{result.message}</p>
      {result.evidence.length > 0 && (
        <ul className="list">{result.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}</ul>
      )}
      {result.error && <p className="failure-text">{result.error}</p>}
    </article>
  );
}
