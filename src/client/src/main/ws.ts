/** WebSocket client with auto-reconnect. */

import WebSocket from "ws";
import { getServerUrl } from "./api";

type EventHandler = (data: Record<string, unknown>) => void;

let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
const handlers: Map<string, EventHandler[]> = new Map();
let connected = false;
let connectedCallback: (() => void) | null = null;

export function onConnected(cb: () => void) {
  connectedCallback = cb;
}

export function isConnected(): boolean {
  return connected;
}

export function on(event: string, handler: EventHandler) {
  if (!handlers.has(event)) handlers.set(event, []);
  handlers.get(event)!.push(handler);
}

export function send(event: string, data: Record<string, unknown> = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ event, ...data }));
  }
}

export function connect() {
  if (ws) return;

  const url = getServerUrl().replace(/^http/, "ws") + "/ws";
  ws = new WebSocket(url);

  ws.on("open", () => {
    connected = true;
    console.log("[ws] connected");
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    connectedCallback?.();
  });

  ws.on("message", (raw: WebSocket.Data) => {
    try {
      const msg = JSON.parse(raw.toString());
      const event = msg.event as string;
      if (event && handlers.has(event)) {
        for (const h of handlers.get(event)!) {
          h(msg);
        }
      }
    } catch {
      // ignore malformed messages
    }
  });

  ws.on("close", () => {
    connected = false;
    ws = null;
    console.log("[ws] disconnected, reconnecting in 2s...");
    scheduleReconnect();
  });

  ws.on("error", (err: Error) => {
    console.error("[ws] error:", err.message);
    ws?.close();
  });
}

export function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    ws.close();
    ws = null;
  }
  connected = false;
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, 2000);
}
