/** Main process: window management, global shortcuts, IPC handlers, child processes. */

import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  screen,
  shell,
} from "electron";
import * as fs from "fs";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";
import { IPC } from "./ipc";
import * as api from "./api";
import * as sse from "./sse";
import { isDev, getDataDir, getPythonPath, getLogDir, getPythonSrcDir, getGoogleTokenPath, getOutlookTokenPath } from "./paths";
import * as bootstrap from "./features/bootstrap";
import { runOnboarding } from "./features/onboarding";
import { setupConnectorIpc } from "./connectors/manager";
import { initUpdateChecker, checkForUpdates } from "./features/updater";

let serverProc: ChildProcess | null = null;

// ── Config seeding ───────────────────────────────────────────

function ensureConfigDefaults(): void {
  const configPath = path.join(getDataDir(), "tada-config.json");
  const defaultsPath = isDev()
    ? path.join(getDataDir(), "tada-config.defaults.json")
    : path.join(process.resourcesPath!, "tada-config.defaults.json");

  let defaults: Record<string, unknown> = {};
  try { defaults = JSON.parse(fs.readFileSync(defaultsPath, "utf-8")); } catch { return; }

  let cfg: Record<string, unknown> = {};
  try { cfg = JSON.parse(fs.readFileSync(configPath, "utf-8")); } catch {}

  let changed = false;
  for (const [key, value] of Object.entries(defaults)) {
    if (!(key in cfg)) { cfg[key] = value; changed = true; }
  }
  if (changed) {
    fs.mkdirSync(path.dirname(configPath), { recursive: true });
    fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2));
  }
}

// ── Server management ─────────────────────────────────────────

function findFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const net = require("net");
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const port = (srv.address() as { port: number }).port;
      srv.close(() => resolve(port));
    });
    srv.on("error", reject);
  });
}

function startServer(port: number): void {
  const logDirPath = getLogDir();
  const pythonPath = getPythonPath();
  const pythonSrcDir = getPythonSrcDir();
  const configPath = path.join(getDataDir(), "tada-config.json");

  const googleTokenPath = getGoogleTokenPath();
  const outlookTokenPath = getOutlookTokenPath();

  if (isDev()) {
    // Dev mode: use uv run from repo root
    const projectRoot = getDataDir();
    serverProc = spawn("uv", [
      "run", "python", "-m", "server",
      "--port", String(port),
      "--log-dir", logDirPath,
      "--google-token-path", googleTokenPath,
      "--outlook-token-path", outlookTokenPath,
      "--save-recordings",
      "--resume-from-checkpoint", "auto",
      "--log-to-wandb",
    ], { cwd: projectRoot, env: { ...process.env, TADA_CONFIG_PATH: configPath } });
  } else {
    // Packaged mode: use venv python directly
    serverProc = spawn(pythonPath, [
      "-m", "server",
      "--port", String(port),
      "--log-dir", logDirPath,
      "--google-token-path", googleTokenPath,
      "--outlook-token-path", outlookTokenPath,
      "--save-recordings",
      "--resume-from-checkpoint", "auto",
      "--log-to-wandb",
    ], {
      env: {
        ...process.env,
        PYTHONPATH: pythonSrcDir,
        TADA_CONFIG_PATH: configPath,
      },
    });
  }

  serverProc.stdout?.on("data", (chunk: Buffer) => {
    process.stdout.write(`[server] ${chunk}`);
  });
  serverProc.stderr?.on("data", (chunk: Buffer) => {
    process.stderr.write(`[server] ${chunk}`);
  });
  serverProc.on("exit", (code) => {
    console.log(`[server] exited with code ${code}`);
    serverProc = null;
  });

  console.log(`[server] spawned on port ${port}, log-dir ${logDirPath}`);
}

function stopServer(): void {
  if (serverProc) {
    serverProc.kill("SIGTERM");
    serverProc = null;
  }
}

function waitForServer(url: string, timeoutMs = 120000): Promise<void> {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    function poll() {
      import("http").then(({ get }) => {
        const req = get(url, (res) => {
          res.resume();
          resolve();
        });
        req.on("error", () => {
          if (Date.now() - start > timeoutMs) {
            reject(new Error("Server did not start in time"));
          } else {
            setTimeout(poll, 500);
          }
        });
        req.end();
      });
    }
    poll();
  });
}

let setupWindow: BrowserWindow | null = null;
let dashboardWindow: BrowserWindow | null = null;
let overlayWindow: BrowserWindow | null = null;
let overlayVisible = false;
let isQuitting = false;

// ── Window creation ──────────────────────────────────────────

function createSetupWindow(): BrowserWindow {
  setupWindow = new BrowserWindow({
    width: 500,
    height: 350,
    title: "Tada",
    titleBarStyle: "hiddenInset",
    backgroundColor: "#F4F2EE",
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  setupWindow.on("closed", () => {
    setupWindow = null;
  });

  return setupWindow;
}

function createDashboard() {
  dashboardWindow = new BrowserWindow({
    width: 900,
    height: 700,
    title: "Tada",
    titleBarStyle: "hiddenInset",
    backgroundColor: "#F4F2EE",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev()) {
    dashboardWindow.loadURL("http://localhost:5173/index.html");
  } else {
    dashboardWindow.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
  }

  dashboardWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  dashboardWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      dashboardWindow?.hide();
    }
  });
}

function createOverlay() {
  const display = screen.getPrimaryDisplay();
  const { width: screenW, height: screenH } = display.workAreaSize;
  const overlayW = 420;
  const overlayH = 80;

  overlayWindow = new BrowserWindow({
    width: overlayW,
    height: overlayH,
    x: screenW - overlayW - 20,
    y: screenH - overlayH - 60,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    resizable: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Click-through + visible on all workspaces
  overlayWindow.setIgnoreMouseEvents(true);
  overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true, skipTransformProcessType: true });

  if (isDev()) {
    overlayWindow.loadURL("http://localhost:5173/overlay.html");
  } else {
    overlayWindow.loadFile(path.join(__dirname, "..", "renderer", "overlay.html"));
  }

  overlayWindow.on("closed", () => {
    overlayWindow = null;
  });
}

function toggleOverlay() {
  if (!overlayWindow) return;
  if (overlayVisible) {
    overlayWindow.hide();
  } else {
    overlayWindow.show();
    // Notify dashboard first (before overlay send which could fail)
    dashboardWindow?.webContents.send(IPC.PREDICTION_REQUESTED);
    api.requestPrediction().catch((err) => console.error("[prediction]", err));
    overlayWindow.webContents.send(IPC.OVERLAY_WAITING);
  }
  overlayVisible = !overlayVisible;
}

function resizeOverlay(contentHeight: number) {
  if (!overlayWindow) return;
  const display = screen.getPrimaryDisplay();
  const { width: screenW, height: screenH } = display.workAreaSize;
  const overlayW = 420;
  const h = Math.max(80, Math.min(500, contentHeight));
  overlayWindow.setBounds({
    x: screenW - overlayW - 20,
    y: screenH - h - 60,
    width: overlayW,
    height: h,
  });
}

// ── SSE event forwarding ─────────────────────────────────────

function setupSseForwarding() {
  // Dashboard subscribes to SSE directly — only forward what it can't receive itself.

  sse.on("prediction", (data) => {
    // Overlay has no direct SSE connection; forward predictions to it via IPC.
    if (overlayVisible && overlayWindow) {
      overlayWindow.webContents.send(IPC.OVERLAY_PREDICTION, data);
    }
  });

  sse.on("moment_completed", (data) => {
    dashboardWindow?.webContents.send(IPC.MOMENT_COMPLETED, data);
  });
}

// ── IPC handlers ─────────────────────────────────────────────

function setupIpc() {
  // Moments
  ipcMain.handle(IPC.MOMENTS_GET_TASKS, () => api.getMomentsTasks());
  ipcMain.handle(IPC.MOMENTS_GET_RESULTS, () => api.getMomentsResults());
  ipcMain.handle(IPC.GET_SERVER_URL, () => api.getServerUrl());

  // Overlay resize
  ipcMain.on("overlay:resize", (_e, height: number) => {
    resizeOverlay(height);
  });

  // Update check
  ipcMain.handle(IPC.UPDATE_CHECK, () => checkForUpdates());
}

// ── Bootstrap ────────────────────────────────────────────────

async function runBootstrap(): Promise<void> {
  const win = createSetupWindow();
  await win.loadFile(path.join(__dirname, "..", "renderer", "setup.html"));

  return new Promise<void>((resolve) => {
    const doBootstrap = async () => {
      try {
        await bootstrap.run(
          (msg, pct) => { win.webContents.send(IPC.BOOTSTRAP_PROGRESS, msg, pct); },
          (line) => { win.webContents.send(IPC.BOOTSTRAP_LOG, line); },
        );
        win.webContents.send(IPC.BOOTSTRAP_COMPLETE);
        await new Promise((r) => setTimeout(r, 1000));
        win.close();
        ipcMain.removeAllListeners(IPC.BOOTSTRAP_RETRY);
        resolve();
      } catch (err: unknown) {
        const errMsg = err instanceof Error ? err.message : String(err);
        console.error("[bootstrap] failed:", errMsg);
        try {
          win.webContents.send(IPC.BOOTSTRAP_ERROR, errMsg);
        } catch {
          console.error("[bootstrap] could not send error to setup window");
        }
        // don't resolve — wait for retry
      }
    };

    ipcMain.on(IPC.BOOTSTRAP_RETRY, () => {
      doBootstrap();
    });

    doBootstrap();
  });
}


// ── App lifecycle ────────────────────────────────────────────

app.whenReady().then(async () => {
  app.dock?.show();
  ensureConfigDefaults();
  setupIpc();
  setupConnectorIpc();

  // In packaged mode, check if bootstrap is needed
  if (!isDev() && !bootstrap.isReady()) {
    await runBootstrap();
  }

  // In dev, the supervisor starts the server and provides the URL.
  // In packaged mode, Electron owns server lifecycle directly.
  const externalDevServerUrl = isDev() ? process.env.TADA_SERVER_URL : undefined;
  if (externalDevServerUrl) {
    api.setServerUrl(externalDevServerUrl);
  } else {
    const port = await findFreePort();
    api.setServerUrl(`http://127.0.0.1:${port}`);
    startServer(port);
  }
  await waitForServer(`${api.getServerUrl()}/api/status`);

  const { complete } = await api.getOnboardingStatus() as { complete: boolean };
  if (!complete) {
    await runOnboarding();
  }

  createDashboard();
  createOverlay();
  setupSseForwarding();

  if (dashboardWindow) {
    initUpdateChecker(dashboardWindow);
  }

  // Re-send SERVER_READY whenever the SSE (re)connects (covers sleep/wake).
  sse.onConnected(() => {
    dashboardWindow?.webContents.send(IPC.SERVER_READY, { url: api.getServerUrl() });
  });

  // Re-send SERVER_READY on renderer reload if already connected (covers HMR).
  dashboardWindow?.webContents.on("did-finish-load", () => {
    if (sse.isConnected()) {
      dashboardWindow?.webContents.send(IPC.SERVER_READY, { url: api.getServerUrl() });
    }
  });

  sse.connect();
  globalShortcut.register("Control+H", toggleOverlay);
});

app.on("before-quit", () => {
  isQuitting = true;
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    sse.disconnect();
    stopServer();
    app.quit();
  }
});

app.on("activate", () => {
  if (dashboardWindow) {
    dashboardWindow.show();
  }
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});
