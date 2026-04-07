/** SSE client — subscribes to /api/events for server-push. Auto-reconnects per the EventSource spec. */

import { createSSEClient } from "../../shared/sse-core";
import { getServerUrl } from "./client";

const client = createSSEClient({
  getUrl: getServerUrl,
  EventSourceCtor: EventSource,
});

export const { on, connect, disconnect, isConnected } = client;
