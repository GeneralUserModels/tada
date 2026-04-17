/** Onboarding window — screen recording permission + completion signal only.
 *
 * All other onboarding work (Google/Outlook OAuth, notifications check,
 * filesystem check, settings save, onboarding_complete flag) happens via
 * direct calls from the renderer to the Python server.
 */

import * as path from "path";
import { app, BrowserWindow, ipcMain, shell } from "electron";
import { isDev } from "../paths";
import { IPC } from "../ipc";
import * as api from "../api";
import { connectorPermissions } from "../connectors/permissions";

let onboardingWindow: BrowserWindow | null = null;

export function getOnboardingWindow(): BrowserWindow | null {
  return onboardingWindow;
}

export function runOnboarding(serverReady?: Promise<void>): Promise<void> {
  return new Promise<void>((resolve) => {
    const win = new BrowserWindow({
      width: 580,
      height: 720,
      title: "Tada",
      titleBarStyle: "hiddenInset",
      backgroundColor: "#F4F2EE",
      resizable: false,
      webPreferences: {
        preload: path.join(__dirname, "..", "..", "preload", "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });

    onboardingWindow = win;

    if (isDev()) {
      win.loadURL("http://localhost:5173/onboarding.html");
    } else {
      win.loadFile(path.join(__dirname, "..", "..", "renderer", "onboarding.html"));
    }

    // Send server URL once both the page and the server are ready.
    // When serverReady is provided, the window can render its shell
    // while the server is still starting up — eliminating the visible
    // gap between the setup window closing and onboarding appearing.
    win.webContents.on("did-finish-load", async () => {
      if (serverReady) await serverReady;
      win.webContents.send(IPC.SERVER_READY, { url: api.getServerUrl() });
    });

    const screen = connectorPermissions.screen!;
    const fda = connectorPermissions.notifications!;

    const handleCheckPermission = async () =>
      (await screen.check()) ? "granted" : "denied";

    const handleRequestScreenPermission = async () =>
      (await screen.request!()) ? "granted" : "denied";

    const handleOpenSettings = () => shell.openExternal(screen.fixUrl);

    const handleOpenFdaSettings = () => shell.openExternal(fda.fixUrl);

    let submitted = false;

    const handleComplete = () => {
      submitted = true;
      win.close();
      cleanup();
      resolve();
    };

    function cleanup() {
      ipcMain.removeHandler(IPC.ONBOARDING_CHECK_SCREEN_PERMISSION);
      ipcMain.removeHandler(IPC.ONBOARDING_OPEN_SCREEN_SETTINGS);
      ipcMain.removeHandler(IPC.ONBOARDING_REQUEST_SCREEN_PERMISSION);
      ipcMain.removeHandler(IPC.ONBOARDING_OPEN_FDA_SETTINGS);
      ipcMain.removeAllListeners(IPC.ONBOARDING_COMPLETE);
    }

    ipcMain.handle(IPC.ONBOARDING_CHECK_SCREEN_PERMISSION, handleCheckPermission);
    ipcMain.handle(IPC.ONBOARDING_OPEN_SCREEN_SETTINGS, handleOpenSettings);
    ipcMain.handle(IPC.ONBOARDING_REQUEST_SCREEN_PERMISSION, handleRequestScreenPermission);
    ipcMain.handle(IPC.ONBOARDING_OPEN_FDA_SETTINGS, handleOpenFdaSettings);
    ipcMain.on(IPC.ONBOARDING_COMPLETE, handleComplete);

    win.on("closed", () => {
      onboardingWindow = null;
      cleanup();
      if (!submitted) {
        app.quit();
      }
    });
  });
}
