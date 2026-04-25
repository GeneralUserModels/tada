/** Shared SSE client factory — used by both main and renderer processes. */

export type EventHandler<T = Record<string, unknown>> = (data: T) => void;

export interface SSEClient {
  /** Subscribe to an SSE event. Pass a type parameter to type the payload at the call site. */
  on: <T = Record<string, unknown>>(event: string, handler: EventHandler<T>) => void;
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
  // Stored as the loose handler type; on() narrows for callers via generics.
  const handlers: Map<string, EventHandler[]> = new Map();
  let connected = false;

  function on<T = Record<string, unknown>>(event: string, handler: EventHandler<T>) {
    if (!handlers.has(event)) handlers.set(event, []);
    handlers.get(event)!.push(handler as EventHandler);
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
