/** Lightweight version checker — compares local version against GitHub Releases. */

import { app, BrowserWindow, net } from "electron";
import { IPC } from "../ipc";

let mainWindow: BrowserWindow | null = null;

const GITHUB_OWNER = "GeneralUserModels";
const GITHUB_REPO = "tada-release";
const CHECK_INTERVAL_MS = 60 * 60 * 1000; // 1 hour

interface GitHubRelease {
  tag_name: string;
}

function stripLeadingV(tag: string): string {
  return tag.startsWith("v") ? tag.slice(1) : tag;
}

function fetchLatestRelease(): Promise<string | null> {
  const url = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest`;
  return new Promise((resolve) => {
    const request = net.request(url);
    request.setHeader("Accept", "application/vnd.github.v3+json");
    request.setHeader("User-Agent", `Tada/${app.getVersion()}`);

    let body = "";
    request.on("response", (response) => {
      if (response.statusCode !== 200) {
        resolve(null);
        response.on("data", () => {});
        return;
      }
      response.on("data", (chunk) => { body += chunk.toString(); });
      response.on("end", () => {
        try {
          const data: GitHubRelease = JSON.parse(body);
          resolve(stripLeadingV(data.tag_name));
        } catch {
          resolve(null);
        }
      });
    });
    request.on("error", () => resolve(null));
    request.end();
  });
}

export async function checkForUpdates(): Promise<void> {
  const latest = await fetchLatestRelease();
  if (!latest) return;

  const current = app.getVersion();
  if (latest !== current) {
    console.log(`[updater] new version available: ${latest} (current: ${current})`);
    mainWindow?.webContents.send(IPC.UPDATE_AVAILABLE, { version: latest });
  }
}

export function initUpdateChecker(win: BrowserWindow): void {
  mainWindow = win;
  checkForUpdates();
  setInterval(checkForUpdates, CHECK_INTERVAL_MS);
}
