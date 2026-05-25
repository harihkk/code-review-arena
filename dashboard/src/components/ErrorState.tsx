export function ErrorState({ message }: { message: string }) {
  return <div className="panel callout failure">{message}</div>;
}
