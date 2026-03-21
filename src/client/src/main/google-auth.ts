/** Google OAuth 2.0 flow for Electron using a loopback redirect and system browser. */

import * as fs from "fs";
import * as path from "path";
import * as http from "http";
import { net, shell } from "electron";
import { getGoogleTokenPath } from "./paths";

export interface GoogleUser {
  name: string;
  email: string;
  googleId: string;
}

interface GoogleToken {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  client_id: string;
  client_secret: string;
  scopes: string[];
}

const SCOPES = [
  "openid",
  "email",
  "profile",
  "https://www.googleapis.com/auth/calendar.readonly",
  "https://www.googleapis.com/auth/gmail.readonly",
];

function writeToken(token: GoogleToken): void {
  const tokenPath = getGoogleTokenPath();
  fs.mkdirSync(path.dirname(tokenPath), { recursive: true });
  fs.writeFileSync(tokenPath, JSON.stringify(token, null, 2), "utf-8");
}

function readToken(): GoogleToken | null {
  const tokenPath = getGoogleTokenPath();
  if (!fs.existsSync(tokenPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(tokenPath, "utf-8")) as GoogleToken;
  } catch {
    return null;
  }
}

export async function startGoogleLogin(
  clientId: string,
  clientSecret: string,
): Promise<GoogleUser> {
  return new Promise((resolve, reject) => {
    const server = http.createServer();

    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as { port: number }).port;
      const redirectUri = `http://localhost:${port}`;

      const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
      authUrl.searchParams.set("client_id", clientId);
      authUrl.searchParams.set("redirect_uri", redirectUri);
      authUrl.searchParams.set("response_type", "code");
      authUrl.searchParams.set("scope", SCOPES.join(" "));
      authUrl.searchParams.set("access_type", "offline");
      authUrl.searchParams.set("prompt", "consent");

      let settled = false;

      // Time out after 2 minutes if user doesn't complete login
      const timeout = setTimeout(() => {
        server.close();
        if (!settled) {
          settled = true;
          reject(new Error("Login timed out"));
        }
      }, 120_000);

      server.on("request", async (req, res) => {
        const url = new URL(req.url!, `http://localhost:${port}`);
        // Ignore non-callback requests (e.g. favicon.ico)
        if (url.pathname !== "/") {
          res.writeHead(404);
          res.end();
          return;
        }

        const code = url.searchParams.get("code");
        const error = url.searchParams.get("error");

        if (error) {
          res.writeHead(200, { "Content-Type": "text/html" });
          res.end("<html><body><h3>Login failed. You can close this tab.</h3></body></html>");
          clearTimeout(timeout);
          server.close();
          if (!settled) {
            settled = true;
            reject(new Error(error));
          }
          return;
        }

        if (!code) {
          res.writeHead(400);
          res.end();
          return;
        }

        res.writeHead(200, { "Content-Type": "text/html" });
        res.end("<html><body><h3>Signed in! You can close this tab.</h3></body></html>");

        try {
          const tokenBody = new URLSearchParams({
            code,
            client_id: clientId,
            client_secret: clientSecret,
            redirect_uri: redirectUri,
            grant_type: "authorization_code",
          });

          const tokenRes = await net.fetch("https://oauth2.googleapis.com/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: tokenBody.toString(),
          });

          if (!tokenRes.ok) {
            throw new Error(`Token exchange failed: ${tokenRes.status}`);
          }

          const tokenData = (await tokenRes.json()) as {
            id_token: string;
            access_token: string;
            refresh_token: string;
            expires_in: number;
          };

          const payload = JSON.parse(
            Buffer.from(tokenData.id_token.split(".")[1], "base64").toString("utf-8"),
          ) as { sub: string; name: string; email: string };

          // Store tokens for use by calendar/gmail connectors
          writeToken({
            access_token: tokenData.access_token,
            refresh_token: tokenData.refresh_token,
            expires_at: Date.now() + (tokenData.expires_in || 3600) * 1000,
            client_id: clientId,
            client_secret: clientSecret,
            scopes: SCOPES,
          });
          startTokenRefreshTimer();

          clearTimeout(timeout);
          server.close();
          if (!settled) {
            settled = true;
            resolve({
              name: payload.name,
              email: payload.email,
              googleId: payload.sub,
            });
          }
        } catch (err) {
          clearTimeout(timeout);
          server.close();
          if (!settled) {
            settled = true;
            reject(err);
          }
        }
      });

      shell.openExternal(authUrl.toString());
    });
  });
}

/** Check if Google tokens are present (calendar/gmail access available). */
export function isGoogleConnected(): boolean {
  return fs.existsSync(getGoogleTokenPath());
}

/**
 * "Connect" Google — tokens are already obtained during sign-in, so this just
 * confirms they exist. Returns true if the token file is present.
 */
export async function connectGoogle(_scope?: string): Promise<boolean> {
  return isGoogleConnected();
}

/** Delete the Google token file and stop the refresh timer. */
export async function disconnectGoogle(): Promise<boolean> {
  const tokenPath = getGoogleTokenPath();
  if (fs.existsSync(tokenPath)) {
    fs.unlinkSync(tokenPath);
  }
  stopTokenRefreshTimer();
  console.log("[google-auth] disconnected");
  return true;
}

/** Refresh the Google access token using the stored refresh token. */
async function refreshToken(): Promise<void> {
  const token = readToken();
  if (!token?.refresh_token) return;

  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: token.refresh_token,
    client_id: token.client_id,
    client_secret: token.client_secret,
  });

  const res = await net.fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!res.ok) {
    throw new Error(`Token refresh failed: ${res.status}`);
  }

  const data = (await res.json()) as { access_token: string; expires_in: number; refresh_token?: string };
  token.access_token = data.access_token;
  if (data.refresh_token) token.refresh_token = data.refresh_token;
  token.expires_at = Date.now() + (data.expires_in || 3600) * 1000;
  writeToken(token);
  console.log("[google-auth] token refreshed");
}

let refreshTimer: ReturnType<typeof setInterval> | null = null;

function startTokenRefreshTimer(): void {
  stopTokenRefreshTimer();
  // Refresh every 45 minutes
  refreshTimer = setInterval(async () => {
    try {
      await refreshToken();
    } catch (err) {
      console.error("[google-auth] token refresh failed:", err);
    }
  }, 45 * 60 * 1000);
}

function stopTokenRefreshTimer(): void {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

/** Call this after app.whenReady() to start the refresh timer and eagerly refresh if expired. */
export function initGoogleAuth(): void {
  if (!isGoogleConnected()) return;
  const token = readToken();
  if (token && token.expires_at - Date.now() < 5 * 60 * 1000) {
    refreshToken().catch((err) => console.error("[google-auth] startup token refresh failed:", err));
  }
  startTokenRefreshTimer();
}
