import { useState } from "react";

export function Notifications() {
  const [messages, setMessages] = useState<string[]>([]);

  async function receive(message: string) {
    await Promise.resolve();
    setMessages(previous => [...previous, message]);
  }

  return <button onClick={() => receive("new")}>{messages.length}</button>;
}

