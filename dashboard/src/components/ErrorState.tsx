export function ErrorState({
  title = "Something failed",
  message,
  action,
}: {
  title?: string;
  message: string;
  action?: () => void;
}) {
  return (
    <section className="panel error-state">
      <p className="eyebrow">Error</p>
      <h1>{title}</h1>
      <p>{message}</p>
      {action ? <button className="button" type="button" onClick={action}>Try again</button> : null}
    </section>
  );
}
