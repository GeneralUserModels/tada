/** Auto-updater — uses electron-updater to download and install updates from GitHub Releases. */

import { BrowserWindow } from "electron";
import { autoUpdater } from "electron-updater";
import { IPC } from "../ipc";

let mainWindow: BrowserWindow | null = null;

const CHECK_INTERVAL_MS = 60 * 60 * 1000; // 1 hour

autoUpdater.autoDownload = true;
autoUpdater.autoInstallOnAppQuit = true;

autoUpdater.on("update-available", (info) => {
  const version = info.version;
  console.log(`[updater] update available: ${version}`);
  mainWindow?.webContents.send(IPC.UPDATE_AVAILABLE, { version });
});

autoUpdater.on("update-downloaded", (info) => {
  const version = info.version;
  console.log(`[updater] update downloaded: ${version}`);
  mainWindow?.webContents.send(IPC.UPDATE_DOWNLOADED, { version });
});

autoUpdater.on("error", (err) => {
  console.log(`[updater] error:`, err.message);
});

export function checkForUpdates(): void {
  autoUpdater.checkForUpdates().catch((err) => {
    console.log(`[updater] check failed:`, err.message);
  });
}

export function installUpdate(): void {
  autoUpdater.quitAndInstall(false, true);
}

export function initUpdateChecker(win: BrowserWindow): void {
  mainWindow = win;
  checkForUpdates();
  setInterval(checkForUpdates, CHECK_INTERVAL_MS);
}
