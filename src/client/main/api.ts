/** REST client — thin fetch wrapper for the PowerNap server. */

import * as http from "http";
import * as https from "https";

let serverUrl = "http://127.0.0.1:8000";

export function setServerUrl(url: string) {
  serverUrl = url.replace(/\/$/, "");
}

export function getServerUrl(): string {
  return serverUrl;
}

async function request(
  method: string,
  path: string,
  body?: unknown
): Promise<unknown> {
  const url = `${serverUrl}${path}`;
  const opts: RequestInit = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) {
    opts.body = JSON.stringify(body);
  }

  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${method} ${path} ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Control ──────────────────────────────────────────────────
export const startRecording = () => request("POST", "/api/control/recording/start");
export const stopRecording = () => request("POST", "/api/control/recording/stop");
export const startTraining = () => request("POST", "/api/control/training/start");
export const stopTraining = () => request("POST", "/api/control/training/stop");
export const startInference = () => request("POST", "/api/control/inference/start");
export const stopInference = () => request("POST", "/api/control/inference/stop");

// ── Status / Settings ────────────────────────────────────────
export const getStatus = () => request("GET", "/api/status");
export const getSettings = () => request("GET", "/api/settings");
export const updateSettings = (data: Record<string, unknown>) =>
  request("PUT", "/api/settings", data);

// ── Training ─────────────────────────────────────────────────
export const getTrainingHistory = () => request("GET", "/api/training/history");
export const getLabelHistory = () => request("GET", "/api/label-history");

// ── Connectors ───────────────────────────────────────────────
export const getConnectors = () =>
  request("GET", "/api/connectors") as Promise<Record<string, { enabled: boolean; error?: string | null; requires_auth?: string | null }>>;

export const updateConnector = (name: string, enabled: boolean) =>
  request("PUT", `/api/connectors/${name}`, { enabled });

// ── Moments ─────────────────────────────────────────────────
export const getMomentsTasks = () => request("GET", "/api/moments/tasks");
export const getMomentsResults = () => request("GET", "/api/moments/results");
export const getMomentResultHtml = (slug: string) =>
  fetch(`${getServerUrl()}/api/moments/results/${slug}/index.html`).then((r) => r.text());

// ── Recordings ───────────────────────────────────────────────
export const postAggregation = (data: unknown) =>
  request("POST", "/api/recordings/aggregation", data);
