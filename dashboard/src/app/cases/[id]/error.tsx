"use client";

import { ErrorState } from "../../../components/ErrorState";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <ErrorState
      title="Unable to load this case"
      message={`${error.message}. The dashboard reads cases from the API; start it with \`arena serve\` and retry.`}
      action={reset}
    />
  );
}
