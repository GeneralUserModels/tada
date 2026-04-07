/** Onboarding window — screen recording permission + completion signal only.
 *
 * All other onboarding work (Google/Outlook OAuth, notifications check,
 * filesystem check, settings save, onboarding_complete flag) happens via
 * direct calls from the renderer to the Python server.
 */

import * as path from "path";
import { app, BrowserWindow, desktopCapturer, ipcMain, shell, systemPreferences } from "electron";
import { isDev } from "../paths";
import { IPC } from "../ipc";
import * as api from "../api";

export function runOnboarding(): Promise<void> {
  return new Promise<void>((resolve) => {
    const win = new BrowserWindow({
      width: 580,
      height: 720,
      title: "PowerNap",
      titleBarStyle: "hiddenInset",
      backgroundColor: "#F4F2EE",
      resizable: false,
      webPreferences: {
        preload: path.join(__dirname, "..", "..", "preload", "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });

    if (isDev()) {
      win.loadURL("http://localhost:5173/onboarding.html");
    } else {
      win.loadFile(path.join(__dirname, "..", "..", "renderer", "onboarding.html"));
    }

    // Send server URL so the renderer can call Python directly
    win.webContents.on("did-finish-load", () => {
      win.webContents.send(IPC.SERVER_READY, { url: api.getServerUrl() });
    });

    const handleCheckPermission = async () => {
      const status = systemPreferences.getMediaAccessStatus("screen");
      if (status !== "granted") return status;
      // Verify with a real capture — getMediaAccessStatus can lie in dev builds
      // (inherits terminal permission) and on macOS Sequoia+.
      try {
        const sources = await desktopCapturer.getSources({
          types: ["screen"],
          thumbnailSize: { width: 1, height: 1 },
        });
        if (!sources.length) return "denied";
        const bmp = sources[0].thumbnail.toBitmap();
        if (bmp.length === 0) return "denied";
        for (let i = 3; i < bmp.length; i += 4) {
          if (bmp[i] !== 0) return "granted";
        }
        return "denied";
      } catch {
        return "denied";
      }
    };

    const handleRequestScreenPermission = async () => {
      try {
        await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 320, height: 240 } });
      } catch {}
      const status = systemPreferences.getMediaAccessStatus("screen");
      if (status !== "granted") {
        shell.openExternal(
          "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
        );
      }
      return status;
    };

    const handleOpenSettings = () => {
      shell.openExternal(
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
      );
    };

    const handleOpenFdaSettings = () => {
      shell.openExternal(
        "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
      );
    };

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
      cleanup();
      if (!submitted) {
        app.quit();
      }
    });
  });
}
