/** Microsoft Outlook auth — MSAL-based OAuth for Mail + Calendar via Graph API. */

import * as fs from "fs";
import * as path from "path";
import * as http from "http";
import * as https from "https";
import * as url from "url";
import * as crypto from "crypto";
import { shell } from "electron";
import { getOutlookTokenPath } from "./paths";
import { MICROSOFT_CLIENT_ID } from "./auth-config";

const SCOPES = ["Mail.Read", "Calendars.Read", "User.Read", "offline_access"];
const AUTHORITY = "https://login.microsoftonline.com/common";
const REDIRECT_PORT = 48215;
const REDIRECT_URI = `http://localhost:${REDIRECT_PORT}/auth/callback`;

interface OutlookToken {
  access_token: string;
  refresh_token: string;
  expires_at: number;
  client_id: string;
  scopes: string[];
}

function readToken(): OutlookToken | null {
  const tokenPath = getOutlookTokenPath();
  if (!fs.existsSync(tokenPath)) return null;
  return JSON.parse(fs.readFileSync(tokenPath, "utf-8")) as OutlookToken;
}

function writeToken(token: OutlookToken): void {
  const tokenPath = getOutlookTokenPath();
  fs.mkdirSync(path.dirname(tokenPath), { recursive: true });
  fs.writeFileSync(tokenPath, JSON.stringify(token, null, 2), "utf-8");
}

function httpsPost(endpoint: string, body: string): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(endpoint);
    const req = https.request({
      hostname: parsed.hostname,
      path: parsed.pathname + parsed.search,
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": Buffer.byteLength(body),
      },
    }, (res) => {
      let data = "";
      res.on("data", (chunk) => { data += chunk; });
      res.on("end", () => {
        if (res.statusCode && res.statusCode >= 400) {
          reject(new Error(`HTTP ${res.statusCode}: ${data}`));
          return;
        }
        resolve(JSON.parse(data));
      });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

/** Interactive OAuth login — opens browser, listens for redirect. */
export async function connectOutlook(): Promise<boolean> {
  const codeVerifier = crypto.randomBytes(32).toString("base64url");
  const codeChallenge = crypto.createHash("sha256").update(codeVerifier).digest("base64url");
  const state = crypto.randomBytes(16).toString("hex");

  const authUrl = `${AUTHORITY}/oauth2/v2.0/authorize?` + new URLSearchParams({
    client_id: MICROSOFT_CLIENT_ID,
    response_type: "code",
    redirect_uri: REDIRECT_URI,
    scope: SCOPES.join(" "),
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    response_mode: "query",
  }).toString();

  return new Promise((resolve) => {
    const server = http.createServer(async (req, res) => {
      const parsed = url.parse(req.url || "", true);
      if (parsed.pathname !== "/auth/callback") {
        res.writeHead(404);
        res.end();
        return;
      }

      const code = parsed.query.code as string | undefined;
      const returnedState = parsed.query.state as string | undefined;

      if (!code || returnedState !== state) {
        res.writeHead(400);
        res.end("Authentication failed — invalid state or missing code.");
        server.close();
        resolve(false);
        return;
      }

      res.writeHead(200, { "Content-Type": "text/html" });
      res.end("<html><body><h3>Authentication successful!</h3><p>You can close this tab.</p></body></html>");
      server.close();

      const tokenResponse = await httpsPost(
        `${AUTHORITY}/oauth2/v2.0/token`,
        new URLSearchParams({
          client_id: MICROSOFT_CLIENT_ID,
          grant_type: "authorization_code",
          code,
          redirect_uri: REDIRECT_URI,
          code_verifier: codeVerifier,
          scope: SCOPES.join(" "),
        }).toString(),
      );

      const expiresIn = (tokenResponse.expires_in as number) || 3600;
      const token: OutlookToken = {
        access_token: tokenResponse.access_token as string,
        refresh_token: tokenResponse.refresh_token as string,
        expires_at: Date.now() + expiresIn * 1000,
        client_id: MICROSOFT_CLIENT_ID,
        scopes: SCOPES,
      };
      writeToken(token);
      console.log("[outlook-auth] login succeeded");
      startTokenRefreshTimer();
      resolve(true);
    });

    server.listen(REDIRECT_PORT, "127.0.0.1", () => {
      console.log("[outlook-auth] listening for OAuth callback on port", REDIRECT_PORT);
      shell.openExternal(authUrl);
    });

    // Timeout after 2 minutes
    setTimeout(() => {
      server.close();
      resolve(false);
    }, 120_000);
  });
}

/** Check if a token file exists. */
export function isOutlookConnected(): boolean {
  return fs.existsSync(getOutlookTokenPath());
}

/** Delete token file. */
export async function disconnectOutlook(): Promise<boolean> {
  const tokenPath = getOutlookTokenPath();
  if (fs.existsSync(tokenPath)) {
    fs.unlinkSync(tokenPath);
  }
  stopTokenRefreshTimer();
  console.log("[outlook-auth] disconnected");
  return true;
}

/** Refresh access token using refresh_token. */
async function refreshToken(): Promise<void> {
  const token = readToken();
  if (!token?.refresh_token) return;

  const tokenResponse = await httpsPost(
    `${AUTHORITY}/oauth2/v2.0/token`,
    new URLSearchParams({
      client_id: MICROSOFT_CLIENT_ID,
      grant_type: "refresh_token",
      refresh_token: token.refresh_token,
      scope: SCOPES.join(" "),
    }).toString(),
  );

  const expiresIn = (tokenResponse.expires_in as number) || 3600;
  token.access_token = tokenResponse.access_token as string;
  if (tokenResponse.refresh_token) {
    token.refresh_token = tokenResponse.refresh_token as string;
  }
  token.expires_at = Date.now() + expiresIn * 1000;
  writeToken(token);
  console.log("[outlook-auth] token refreshed");
}

let refreshTimer: ReturnType<typeof setInterval> | null = null;

function startTokenRefreshTimer(): void {
  stopTokenRefreshTimer();
  // Refresh every 45 minutes
  refreshTimer = setInterval(async () => {
    try {
      await refreshToken();
    } catch (err) {
      console.error("[outlook-auth] token refresh failed:", err);
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
export function initOutlookAuth(): void {
  if (!isOutlookConnected()) return;
  const token = readToken();
  if (token && token.expires_at - Date.now() < 5 * 60 * 1000) {
    refreshToken().catch((err) => console.error("[outlook-auth] startup token refresh failed:", err));
  }
  startTokenRefreshTimer();
}
