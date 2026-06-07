// Display-layer naming for reviewers. Internal IDs (e.g. "mock" + model
// "perfect_patch") stay as recorded in run/report data; this module only maps
// them to presentation labels for the dashboard.

export type ReviewerIdentity = { reviewer: string; model?: string | null };

export type ReviewerType = "control" | "reference" | "custom" | "external";

const CONTROL_DISPLAY_NAMES: Record<string, string> = {
  perfect_patch: "Control: Perfect Repair",
  keyword_gamer: "Control: Keyword Gamer",
  bad_patch: "Control: Weak Repair",
  detects_no_patch: "Control: Detection Only",
  malformed_patch: "Control: Malformed Patch",
  false_positive_patch: "Control: False Positive",
};

const DISPLAY_NAMES: Record<string, string> = {
  "reference-patch": "Reference Patch",
  "custom-command": "Custom Command",
};

export const CONTROL_BASELINE_NOTE =
  "Control baselines are deterministic harness checks, not external model results.";

/** The internal reviewer:model slug, e.g. "mock:perfect_patch". Not for display. */
export function reviewerSlug({ reviewer, model }: ReviewerIdentity): string {
  return reviewer === "mock" && model ? `mock:${model}` : reviewer;
}

/** Inverse of {@link reviewerSlug}: recovers an identity from a stored slug key. */
export function identityFromSlug(slug: string): ReviewerIdentity {
  const separator = slug.indexOf(":");
  if (separator === -1) return { reviewer: slug };
  return {
    reviewer: slug.slice(0, separator),
    model: slug.slice(separator + 1),
  };
}

export function isControlBaseline({
  reviewer,
  model,
}: ReviewerIdentity): boolean {
  return reviewer === "mock" && Boolean(model);
}

export function reviewerType({
  reviewer,
  model,
}: ReviewerIdentity): ReviewerType {
  if (isControlBaseline({ reviewer, model })) return "control";
  if (reviewer === "reference-patch") return "reference";
  if (reviewer === "custom-command") return "custom";
  return "external";
}

export function reviewerDisplayName(identity: ReviewerIdentity): string {
  const { reviewer, model } = identity;
  if (reviewer === "mock" && model) {
    return CONTROL_DISPLAY_NAMES[model] ?? `Control: ${titleCase(model)}`;
  }
  return DISPLAY_NAMES[reviewer] ?? reviewer;
}

function titleCase(value: string): string {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}
