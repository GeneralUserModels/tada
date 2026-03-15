/** Auto-updater — checks GitHub Releases for new versions. */

import { autoUpdater } from "electron-updater";
import { BrowserWindow, shell } from "electron";
import { IPC } from "./ipc";

let mainWindow: BrowserWindow | null = null;

export function initAutoUpdater(win: BrowserWindow): void {
  mainWindow = win;

  autoUpdater.autoDownload = false;

  autoUpdater.on("update-available", (info) => {
    console.log("[updater] update available:", info.version);
    const releaseUrl =
      `https://github.com/GeneralUserModels/powernap-release/releases/tag/v${info.version}`;
    mainWindow?.webContents.send(IPC.UPDATE_AVAILABLE, {
      version: info.version,
      releaseNotes: info.releaseNotes,
      releaseUrl,
    });
  });

  autoUpdater.on("error", (err) => {
    console.error("[updater] error:", err.message);
    mainWindow?.webContents.send(IPC.UPDATE_ERROR, err.message);
  });

  autoUpdater.checkForUpdates();

  // Re-check every 30 minutes
  setInterval(() => autoUpdater.checkForUpdates(), 30 * 60 * 1000);
}

export function openReleasePage(url: string): void {
  shell.openExternal(url);
}

export function checkForUpdates(): void {
  autoUpdater.checkForUpdates();
}
