import { useState } from "react";

export function Notifications() {
  const [messages, setMessages] = useState<string[]>([]);

  async function receive(message: string) {
    await Promise.resolve();
    setMessages([...messages, message]);
  }

  return <button onClick={() => receive("new")}>{messages.length}</button>;
}

