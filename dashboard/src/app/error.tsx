"use client";

import { ErrorState } from "../components/ErrorState";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return <ErrorState title="Unable to load this page" message={error.message} action={reset} />;
}
