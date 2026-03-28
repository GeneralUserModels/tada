/** First-launch onboarding: collects API keys, model selection, and screen recording permission. */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { app, BrowserWindow, desktopCapturer, ipcMain, shell, systemPreferences } from "electron";
import { getDataDir, isDev } from "../paths";
import { IPC } from "../ipc";
import { startGoogleLogin, connectGoogle } from "../auth/google";
import { connectOutlook } from "../auth/outlook";
import { canReadNotifications } from "./notifications";
import { upsertUser } from "../auth/supabase";
import { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SUPABASE_URL, SUPABASE_ANON_KEY } from "../auth/config";

export interface ConnectorState {
  screen: boolean;
  calendar: boolean;
  gmail: boolean;
  outlook_calendar: boolean;
  outlook_email: boolean;
  notifications: boolean;
  filesystem: boolean;
}

interface OnboardingConfig {
  reward_llm: string;
  default_llm_api_key: string;
  tinker_api_key?: string;
  wandb_api_key?: string;
  user_name?: string;
  user_email?: string;
  connectors: ConnectorState;
  google_configured?: { calendar: boolean; gmail: boolean };
  outlook_configured?: { calendar: boolean; email: boolean };
}

function getSentinelPath(): string {
  return path.join(getDataDir(), ".onboarding-complete");
}

function getConfigPath(): string {
  return path.join(getDataDir(), "powernap-config.json");
}

export function isComplete(): boolean {
  return fs.existsSync(getSentinelPath());
}

export function getConfig(): OnboardingConfig | null {
  try {
    const raw = fs.readFileSync(getConfigPath(), "utf-8");
    return JSON.parse(raw) as OnboardingConfig;
  } catch {
    return null;
  }
}

function saveConfig(data: OnboardingConfig): void {
  const dataDir = getDataDir();
  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(getConfigPath(), JSON.stringify(data, null, 2), "utf-8");
  fs.writeFileSync(getSentinelPath(), new Date().toISOString(), "utf-8");
}

/** Mark specific Google connectors as configured (called when user connects from dashboard). */
export function markGoogleConfigured(calendar?: boolean, gmail?: boolean): void {
  const config = getConfig();
  if (!config) return;
  if (!config.google_configured) config.google_configured = { calendar: false, gmail: false };
  if (calendar !== undefined) config.google_configured.calendar = calendar;
  if (gmail !== undefined) config.google_configured.gmail = gmail;
  fs.writeFileSync(getConfigPath(), JSON.stringify(config, null, 2), "utf-8");
}

function canWatchFilesystem(): boolean {
  const dirs = ["Desktop", "Documents", "Downloads"];
  return dirs.some(d => {
    try {
      fs.accessSync(path.join(os.homedir(), d), fs.constants.R_OK);
      return true;
    } catch { return false; }
  });
}

export function runOnboarding(): Promise<void> {
  return new Promise<void>((resolve) => {
    const win = new BrowserWindow({
      width: 520,
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

    const handleCheckPermission = () => {
      return systemPreferences.getMediaAccessStatus("screen");
    };

    const handleRequestScreenPermission = async () => {
      // Use a real thumbnail size so macOS registers the capture attempt
      try {
        await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 320, height: 240 } });
      } catch {}
      const status = systemPreferences.getMediaAccessStatus("screen");
      // On macOS Sequoia+, open System Settings directly so the user can toggle it
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

    const handleGoogleLogin = async () => {
      try {
        const user = await startGoogleLogin(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET);
        console.log("[onboarding] Google login succeeded:", user.email);
        await upsertUser(SUPABASE_URL, SUPABASE_ANON_KEY, user);
        console.log("[onboarding] Supabase upsert succeeded");
        return { name: user.name, email: user.email };
      } catch (err) {
        console.error("[onboarding] Google login error:", err);
        throw err;
      }
    };

    const handleConnectGoogle = async (_e: Electron.IpcMainInvokeEvent, scope?: string) => {
      return connectGoogle(scope || "calendar,gmail");
    };

    const handleConnectOutlook = async () => {
      return connectOutlook();
    };

    const handleCheckNotifications = () => {
      return canReadNotifications();
    };

    const handleCheckFilesystem = () => {
      return canWatchFilesystem();
    };

    const handleSubmit = (_e: Electron.IpcMainInvokeEvent, data: OnboardingConfig) => {
      saveConfig(data);
      win.close();
      cleanup();
      resolve();
    };

    function cleanup() {
      ipcMain.removeHandler(IPC.ONBOARDING_CHECK_SCREEN_PERMISSION);
      ipcMain.removeHandler(IPC.ONBOARDING_OPEN_SCREEN_SETTINGS);
      ipcMain.removeHandler(IPC.ONBOARDING_REQUEST_SCREEN_PERMISSION);
      ipcMain.removeHandler(IPC.ONBOARDING_GOOGLE_LOGIN);
      ipcMain.removeHandler(IPC.ONBOARDING_CONNECT_GOOGLE);
      ipcMain.removeHandler(IPC.ONBOARDING_CONNECT_OUTLOOK);
      ipcMain.removeHandler(IPC.ONBOARDING_CHECK_NOTIFICATIONS);
      ipcMain.removeHandler(IPC.ONBOARDING_CHECK_FILESYSTEM);
      ipcMain.removeHandler(IPC.ONBOARDING_OPEN_FDA_SETTINGS);
      ipcMain.removeHandler(IPC.ONBOARDING_SUBMIT);
    }

    ipcMain.handle(IPC.ONBOARDING_CHECK_SCREEN_PERMISSION, handleCheckPermission);
    ipcMain.handle(IPC.ONBOARDING_OPEN_SCREEN_SETTINGS, handleOpenSettings);
    ipcMain.handle(IPC.ONBOARDING_REQUEST_SCREEN_PERMISSION, handleRequestScreenPermission);
    ipcMain.handle(IPC.ONBOARDING_GOOGLE_LOGIN, handleGoogleLogin);
    ipcMain.handle(IPC.ONBOARDING_CONNECT_GOOGLE, handleConnectGoogle);
    ipcMain.handle(IPC.ONBOARDING_CONNECT_OUTLOOK, handleConnectOutlook);
    ipcMain.handle(IPC.ONBOARDING_CHECK_NOTIFICATIONS, handleCheckNotifications);
    ipcMain.handle(IPC.ONBOARDING_CHECK_FILESYSTEM, handleCheckFilesystem);
    ipcMain.handle(IPC.ONBOARDING_OPEN_FDA_SETTINGS, handleOpenFdaSettings);
    ipcMain.handle(IPC.ONBOARDING_SUBMIT, handleSubmit);

    win.on("closed", () => {
      cleanup();
      // If window closed without submitting, quit the app
      if (!isComplete()) {
        app.quit();
      }
    });
  });
}
