/** Auto-updater — checks GitHub Releases for new versions. */

import { autoUpdater } from "electron-updater";
import { BrowserWindow } from "electron";
import { IPC } from "./ipc";

let mainWindow: BrowserWindow | null = null;

export function initAutoUpdater(win: BrowserWindow): void {
  mainWindow = win;

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("update-downloaded", (info) => {
    console.log("[updater] update downloaded:", info.version);
    mainWindow?.webContents.send(IPC.UPDATE_DOWNLOADED, { version: info.version });
  });

  autoUpdater.on("error", (err) => {
    console.error("[updater] error:", err.message);
    mainWindow?.webContents.send(IPC.UPDATE_ERROR, err.message);
  });

  autoUpdater.checkForUpdates();

  // Re-check every 30 minutes
  setInterval(() => autoUpdater.checkForUpdates(), 30 * 60 * 1000);
}

export function installNow(): void {
  autoUpdater.quitAndInstall(false, true);
}

export function installOnNextLaunch(): void {
  autoUpdater.autoInstallOnAppQuit = true;
}

export function dismissUpdate(): void {
  autoUpdater.autoInstallOnAppQuit = false;
}

export function checkForUpdates(): void {
  autoUpdater.checkForUpdates();
}
