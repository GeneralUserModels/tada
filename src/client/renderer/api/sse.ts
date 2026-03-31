/** SSE client — subscribes to /api/events for server-push. Auto-reconnects per the EventSource spec. */

import { getServerUrl } from "./client";

type EventHandler = (data: Record<string, unknown>) => void;

let es: EventSource | null = null;
const handlers: Map<string, EventHandler[]> = new Map();
let connected = false;

export function isConnected(): boolean {
  return connected;
}

export function on(event: string, handler: EventHandler) {
  if (!handlers.has(event)) handlers.set(event, []);
  handlers.get(event)!.push(handler);
}

export function connect() {
  if (es) return;

  const url = `${getServerUrl()}/api/events`;
  const source = new EventSource(url);

  source.onopen = () => {
    connected = true;
    console.log("[sse] connected");
  };

  source.onmessage = (e: MessageEvent) => {
    try {
      const msg = JSON.parse(e.data);
      const event = msg.event as string;
      if (event && handlers.has(event)) {
        for (const h of handlers.get(event)!) {
          h(msg);
        }
      }
    } catch {
      // ignore malformed messages
    }
  };

  source.onerror = () => {
    connected = false;
    console.log("[sse] error / reconnecting...");
    // EventSource reconnects automatically per the spec — no manual retry needed
  };

  es = source;
}

export function disconnect() {
  if (es) {
    es.close();
    es = null;
  }
  connected = false;
}
