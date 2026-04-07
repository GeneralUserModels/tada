/** Shared SSE client factory — used by both main and renderer processes. */

export type EventHandler = (data: Record<string, unknown>) => void;

export interface SSEClient {
  on: (event: string, handler: EventHandler) => void;
  connect: () => void;
  disconnect: () => void;
  isConnected: () => boolean;
}

interface SSEClientOptions {
  getUrl: () => string;
  EventSourceCtor: typeof EventSource;
  onConnected?: () => void;
}

export function createSSEClient(opts: SSEClientOptions): SSEClient {
  let es: InstanceType<typeof EventSource> | null = null;
  const handlers: Map<string, EventHandler[]> = new Map();
  let connected = false;

  function on(event: string, handler: EventHandler) {
    if (!handlers.has(event)) handlers.set(event, []);
    handlers.get(event)!.push(handler);
  }

  function connect() {
    if (es) return;

    const source = new opts.EventSourceCtor(`${opts.getUrl()}/api/events`);

    source.onopen = () => {
      connected = true;
      console.log("[sse] connected");
      opts.onConnected?.();
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
    };

    es = source;
  }

  function disconnect() {
    if (es) {
      es.close();
      es = null;
    }
    connected = false;
  }

  return { on, connect, disconnect, isConnected: () => connected };
}
