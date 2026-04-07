/** SSE client — subscribes to /api/events for server-push. Auto-reconnects per the EventSource spec. */

import { EventSource } from "eventsource";
import { getServerUrl } from "./api";
import { createSSEClient } from "../shared/sse-core";

let connectedCallback: (() => void) | null = null;

export function onConnected(cb: () => void) {
  connectedCallback = cb;
}

const client = createSSEClient({
  getUrl: getServerUrl,
  EventSourceCtor: EventSource as unknown as typeof globalThis.EventSource,
  onConnected: () => connectedCallback?.(),
});

export const { on, connect, disconnect, isConnected } = client;
