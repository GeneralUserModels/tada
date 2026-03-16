/** First-launch onboarding: collects API keys, model selection, and screen recording permission. */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { app, BrowserWindow, desktopCapturer, ipcMain, shell, systemPreferences } from "electron";
import { getDataDir } from "./paths";
import { IPC } from "./ipc";
import { startGoogleLogin } from "./google-auth";
import { connectGoogle } from "./gws-auth";
import { connectOutlook } from "./outlook-auth";
import { canReadNotifications } from "./notifications";
import { upsertUser } from "./supabase";
import { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SUPABASE_URL, SUPABASE_ANON_KEY } from "./auth-config";

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
  gemini_api_key: string;
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
        preload: path.join(__dirname, "..", "preload", "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
      },
    });

    win.loadFile(path.join(__dirname, "..", "renderer", "onboarding.html"));

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
