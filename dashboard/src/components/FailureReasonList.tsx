const labels: Record<string, string> = {
  detection_failed: "Seeded bug was not detected",
  localization_failed: "Finding was not localized to the expected code",
  patch_required_but_missing: "Patch required but missing",
  patch_apply_failed: "Patch did not apply cleanly",
  tests_failed: "Regression tests did not pass",
  structural_validation_failed: "Structural validation failed",
  false_positive: "Unmatched finding exceeded the allowed threshold",
};

// Short form for compact contexts (report cards, chart labels) where the
// long descriptive sentences above would wrap or crowd the layout.
const shortLabels: Record<string, string> = {
  detection_failed: "Detection failed",
  localization_failed: "Localization failed",
  patch_required_but_missing: "Patch missing",
  patch_apply_failed: "Patch apply failed",
  tests_failed: "Tests failed",
  structural_validation_failed: "Structural validation failed",
  false_positive: "False positive",
};

export function shortFailureLabel(reason: string): string {
  return shortLabels[reason] ?? reason.replaceAll("_", " ");
}

export function FailureReasonList({ reasons }: { reasons: string[] }) {
  if (!reasons.length)
    return <p className="pass-text">No validation failures.</p>;
  return (
    <ul className="reason-list">
      {reasons.map((reason) => (
        <li key={reason}>
          <code>{reason}</code>
          <span>{labels[reason] ?? reason.replaceAll("_", " ")}</span>
        </li>
      ))}
    </ul>
  );
}
