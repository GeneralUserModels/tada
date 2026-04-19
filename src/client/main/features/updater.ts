/** Auto-updater — uses electron-updater to download and install updates from GitHub Releases. */

import { app, BrowserWindow } from "electron";
import { autoUpdater } from "electron-updater";
import { IPC } from "../ipc";

let mainWindow: BrowserWindow | null = null;
let pendingVersion: string | null = null;
let pendingDownloaded = false;

const CHECK_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

autoUpdater.autoDownload = true;
autoUpdater.autoInstallOnAppQuit = true;
autoUpdater.channel = app.getVersion().split("-")[1] ?? "latest";

autoUpdater.on("update-available", (info) => {
  pendingVersion = info.version;
  pendingDownloaded = false;
  console.log(`[updater] update available: ${pendingVersion}`);
  mainWindow?.webContents.send(IPC.UPDATE_AVAILABLE, { version: pendingVersion });
});

autoUpdater.on("download-progress", (progress) => {
  mainWindow?.webContents.send(IPC.UPDATE_PROGRESS, {
    percent: progress.percent,
    transferred: progress.transferred,
    total: progress.total,
    bytesPerSecond: progress.bytesPerSecond,
  });
});

autoUpdater.on("update-downloaded", (info) => {
  pendingVersion = info.version;
  pendingDownloaded = true;
  console.log(`[updater] update downloaded: ${pendingVersion}`);
  mainWindow?.webContents.send(IPC.UPDATE_DOWNLOADED, { version: pendingVersion });
});

autoUpdater.on("error", (err) => {
  console.log(`[updater] error:`, err.message);
  mainWindow?.webContents.send(IPC.UPDATE_ERROR, { message: err.message });
});

function resendPendingUpdate(): void {
  if (!pendingVersion || !mainWindow) return;
  mainWindow.webContents.send(IPC.UPDATE_AVAILABLE, { version: pendingVersion });
  if (pendingDownloaded) {
    mainWindow.webContents.send(IPC.UPDATE_DOWNLOADED, { version: pendingVersion });
  }
}

export function checkForUpdates(): void {
  autoUpdater.checkForUpdates().catch((err) => {
    console.log(`[updater] check failed:`, err.message);
    // Still re-surface a previously found update even if the check failed
    resendPendingUpdate();
  });
}

export function installUpdate(): void {
  // Force isSilent=false so electron-updater calls app.quit() internally,
  // and isForceRunAfter=true so the new version launches after install.
  autoUpdater.quitAndInstall(false, true);
}

export function initUpdateChecker(win: BrowserWindow): void {
  mainWindow = win;
  checkForUpdates();
  setInterval(() => {
    resendPendingUpdate();
    checkForUpdates();
  }, CHECK_INTERVAL_MS);
}
