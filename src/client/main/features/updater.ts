/** Auto-updater — uses electron-updater to download and install updates from GitHub Releases. */

import { app, BrowserWindow } from "electron";
import { autoUpdater } from "electron-updater";
import { IPC } from "../ipc";

let mainWindow: BrowserWindow | null = null;
let pendingVersion: string | null = null;
let pendingDownloaded = false;
let beforeInstall: () => void = () => {};

const CHECK_INTERVAL_MS = 10 * 60 * 1000; // 10 minutes

// Strict channel siloing: alpha builds only see alpha releases, beta only beta,
// stable only stable. The GitHub provider would otherwise cascade alpha → beta
// → latest, surfacing higher-channel versions to lower-channel users.
function channelOfVersion(v: string): string {
  const m = v.match(/-([a-z]+)/i);
  return m?.[1]?.toLowerCase() ?? "latest";
}

const ourChannel = channelOfVersion(app.getVersion());

// We gate downloads ourselves in `update-available` so cross-channel updates
// are dropped before any bytes are pulled.
autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = true;
autoUpdater.channel = ourChannel;

autoUpdater.on("update-available", (info) => {
  const incomingChannel = channelOfVersion(info.version);
  if (incomingChannel !== ourChannel) {
    console.log(`[updater] skipping cross-channel update ${info.version} (${incomingChannel} != ${ourChannel})`);
    return;
  }
  pendingVersion = info.version;
  pendingDownloaded = false;
  console.log(`[updater] update available: ${pendingVersion}`);
  mainWindow?.webContents.send(IPC.UPDATE_AVAILABLE, { version: pendingVersion });
  autoUpdater.downloadUpdate().catch((e) => console.log(`[updater] download failed:`, e?.message));
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
  // Squirrel.Mac closes windows but does not synthesise `before-quit`, so the
  // dashboard window's close handler (which calls preventDefault unless
  // isQuitting=true) would swallow the close and leave the app hidden while
  // Squirrel waits forever to install. The callback flips that flag and stops
  // the Python server before we hand control to the native updater.
  beforeInstall();
  autoUpdater.quitAndInstall(false, true);
  // Safety net: if the native quit path stalls, force-quit so the user is
  // never stranded on "Installing…".
  setTimeout(() => app.quit(), 5000);
}

export function initUpdateChecker(win: BrowserWindow, onBeforeInstall: () => void): void {
  mainWindow = win;
  beforeInstall = onBeforeInstall;
  checkForUpdates();
  setInterval(() => {
    resendPendingUpdate();
    checkForUpdates();
  }, CHECK_INTERVAL_MS);
}
