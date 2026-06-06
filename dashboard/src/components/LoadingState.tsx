export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="skeleton-panel" aria-live="polite" aria-busy="true">
      <span>{label}</span>
      <div />
      <div />
      <div />
    </div>
  );
}
