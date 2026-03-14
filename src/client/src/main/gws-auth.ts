/** Google Workspace CLI auth — connect/disconnect/status via `gws`. */

import { spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import * as https from "https";
import { shell } from "electron";
import { getGwsPath, getDataDir } from "./paths";
import { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET } from "./auth-config";

/** Download a file, following redirects */
function downloadFile(url: string, dest: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    const request = (reqUrl: string) => {
      https.get(reqUrl, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          request(res.headers.location!);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`Download failed: HTTP ${res.statusCode}`));
          return;
        }
        res.pipe(file);
        file.on("finish", () => { file.close(); resolve(); });
      }).on("error", (err) => {
        fs.unlink(dest, () => {});
        reject(err);
      });
    };
    request(url);
  });
}

function runCommand(cmd: string, args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, { stdio: "pipe" });
    proc.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${cmd} exited with code ${code}`));
    });
    proc.on("error", reject);
  });
}

/** Download gws binary if not present */
async function ensureGwsBinary(): Promise<string> {
  const gwsPath = getGwsPath();
  if (fs.existsSync(gwsPath)) return gwsPath;

  console.log("[gws-auth] gws binary not found, downloading...");
  const dataDir = getDataDir();
  const arch = process.arch === "arm64" ? "aarch64" : "x86_64";
  const gwsUrl = `https://github.com/googleworkspace/cli/releases/download/v0.13.3/gws-${arch}-apple-darwin.tar.gz`;
  const tarPath = path.join(dataDir, "gws.tar.gz");

  await downloadFile(gwsUrl, tarPath);
  await runCommand("tar", ["xzf", tarPath, "-C", dataDir]);
  fs.unlinkSync(tarPath);

  const extractedDir = path.join(dataDir, `gws-${arch}-apple-darwin`);
  if (fs.existsSync(path.join(extractedDir, "gws"))) {
    fs.renameSync(path.join(extractedDir, "gws"), gwsPath);
    fs.rmSync(extractedDir, { recursive: true });
  }
  fs.chmodSync(gwsPath, 0o755);
  console.log("[gws-auth] gws binary installed at", gwsPath);
  return gwsPath;
}

/** Write client_secret.json for gws — always ensures correct format */
export function ensureGwsClientSecret(): void {
  const configDir = path.join(os.homedir(), ".config", "gws");
  const secretPath = path.join(configDir, "client_secret.json");

  // Extract project number from client ID (digits before the first dash)
  const projectNumber = GOOGLE_CLIENT_ID.split("-")[0];

  const expected = {
    installed: {
      client_id: GOOGLE_CLIENT_ID,
      project_id: `powernap-${projectNumber}`,
      client_secret: GOOGLE_CLIENT_SECRET,
      auth_uri: "https://accounts.google.com/o/oauth2/auth",
      token_uri: "https://oauth2.googleapis.com/token",
      auth_provider_x509_cert_url: "https://www.googleapis.com/oauth2/v1/certs",
      redirect_uris: ["http://localhost"],
    }
  };

  // Check if existing file matches expected format
  if (fs.existsSync(secretPath)) {
    try {
      const existing = JSON.parse(fs.readFileSync(secretPath, "utf-8"));
      if (existing?.installed?.project_id && existing?.installed?.client_id === GOOGLE_CLIENT_ID) {
        return; // Already valid
      }
    } catch { /* corrupt file, overwrite */ }
  }

  fs.mkdirSync(configDir, { recursive: true });
  fs.writeFileSync(secretPath, JSON.stringify(expected, null, 2));
}

/** Run `gws auth login` — intercept OAuth URL via BROWSER env var and open in system browser */
export async function connectGoogle(scope: string = "calendar,gmail"): Promise<boolean> {
  try {
    await ensureGwsBinary();
    ensureGwsClientSecret();
  } catch (err) {
    console.error("[gws-auth] setup failed:", err);
    return false;
  }

  // Create temp script to intercept browser opening via BROWSER env var.
  // gws (Rust webbrowser crate) checks BROWSER before falling back to `open`.
  const urlFile = path.join(os.tmpdir(), `powernap-oauth-url-${Date.now()}`);
  const browserScript = path.join(os.tmpdir(), `powernap-browser-${Date.now()}.sh`);
  fs.writeFileSync(browserScript, `#!/bin/sh\nprintf '%s' "$1" > "${urlFile}"\n`);
  fs.chmodSync(browserScript, 0o755);

  return new Promise((resolve) => {
    const gwsPath = getGwsPath();
    const proc = spawn(gwsPath, ["auth", "login", "-s", scope], {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, BROWSER: browserScript },
    });

    let stdout = "";
    let stderr = "";
    let browserOpened = false;

    function tryOpenUrl(url: string) {
      if (!browserOpened) {
        browserOpened = true;
        console.log("[gws-auth] opening OAuth URL in browser");
        shell.openExternal(url);
      }
    }

    function cleanupTempFiles() {
      try { fs.unlinkSync(urlFile); } catch {}
      try { fs.unlinkSync(browserScript); } catch {}
    }

    // Poll for URL file written by our BROWSER script
    const urlPoll = setInterval(() => {
      try {
        const url = fs.readFileSync(urlFile, "utf-8").trim();
        if (url) tryOpenUrl(url);
      } catch {}
    }, 200);

    const timeout = setTimeout(() => {
      console.error("[gws-auth] login timed out after 2 minutes");
      proc.kill();
    }, 120_000);

    // Fallback: also scan stdout/stderr for OAuth URLs
    const URL_RE = /(https:\/\/accounts\.google\.com\/o\/oauth2[^\s"'<>]+)/;

    proc.stdout?.on("data", (c: Buffer) => {
      const chunk = c.toString();
      stdout += chunk;
      console.log("[gws-auth] stdout:", chunk.trim());
      const m = chunk.match(URL_RE);
      if (m) tryOpenUrl(m[1]);
    });

    proc.stderr?.on("data", (c: Buffer) => {
      const chunk = c.toString();
      stderr += chunk;
      console.log("[gws-auth] stderr:", chunk.trim());
      const m = chunk.match(URL_RE);
      if (m) tryOpenUrl(m[1]);
    });

    proc.on("exit", (code) => {
      clearTimeout(timeout);
      clearInterval(urlPoll);
      cleanupTempFiles();
      if (code === 0) {
        console.log("[gws-auth] login succeeded");
        resolve(true);
      } else {
        console.error("[gws-auth] login failed (exit " + code + "):", stderr || stdout);
        resolve(false);
      }
    });

    proc.on("error", (err) => {
      clearTimeout(timeout);
      clearInterval(urlPoll);
      cleanupTempFiles();
      console.error("[gws-auth] spawn error:", err.message);
      resolve(false);
    });
  });
}

/** Check if gws has valid credentials (may be .json or .enc depending on gws version) */
export function isGoogleConnected(): boolean {
  const configDir = path.join(os.homedir(), ".config", "gws");
  return (
    fs.existsSync(path.join(configDir, "credentials.json")) ||
    fs.existsSync(path.join(configDir, "credentials.enc"))
  );
}

/** Revoke gws credentials */
export async function disconnectGoogle(): Promise<boolean> {
  try {
    const gwsPath = await ensureGwsBinary();
    return new Promise((resolve) => {
      const proc = spawn(gwsPath, ["auth", "revoke"], { stdio: "pipe" });
      proc.on("exit", (code) => resolve(code === 0));
      proc.on("error", (err) => {
        console.error("[gws-auth] revoke error:", err.message);
        resolve(false);
      });
    });
  } catch {
    return false;
  }
}
