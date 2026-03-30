/** Shared REST client core — serverUrl state and fetch wrapper. */

let serverUrl = "";

export function setServerUrl(url: string) {
  serverUrl = url.replace(/\/$/, "");
}

export function getServerUrl(): string {
  return serverUrl;
}

export async function request(
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
