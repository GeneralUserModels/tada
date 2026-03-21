/** Main process: window management, global shortcuts, IPC handlers, child processes. */

import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  screen,
} from "electron";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";
import { IPC } from "./ipc";
import * as api from "./api";
import * as ws from "./ws";
import * as recorder from "./recorder";
import { isDev, getDataDir, getPythonPath, getLogDir, getPythonSrcDir, getGoogleTokenPath, getOutlookTokenPath } from "./paths";
import * as bootstrap from "./bootstrap";
import * as onboarding from "./onboarding";
import { setupConnectorIpc } from "./connector-manager";
import { initGoogleAuth } from "./google-auth";
import { initOutlookAuth } from "./outlook-auth";
import { initAutoUpdater, installNow, installOnNextLaunch, dismissUpdate, checkForUpdates } from "./updater";

let serverProc: ChildProcess | null = null;

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
    ], { cwd: projectRoot });
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

function waitForServer(url: string, timeoutMs = 30000): Promise<void> {
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

  setupWindow.on("closed", () => {
    setupWindow = null;
  });

  return setupWindow;
}

function createDashboard() {
  dashboardWindow = new BrowserWindow({
    width: 900,
    height: 700,
    title: "PowerNap",
    titleBarStyle: "hiddenInset",
    backgroundColor: "#F4F2EE",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  dashboardWindow.loadFile(
    path.join(__dirname, "..", "renderer", "index.html")
  );

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
  overlayWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  overlayWindow.loadFile(
    path.join(__dirname, "..", "renderer", "overlay.html")
  );

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
    ws.send("request_prediction");
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

// ── WebSocket event forwarding ───────────────────────────────

function setupWsForwarding() {
  ws.on("prediction", (data) => {
    dashboardWindow?.webContents.send(IPC.PREDICTION, data);
    if (overlayVisible && overlayWindow) {
      overlayWindow.webContents.send(IPC.OVERLAY_PREDICTION, data);
    }
  });

  ws.on("score", (data) => {
    dashboardWindow?.webContents.send(IPC.SCORE, data);
  });

  ws.on("elbo_score", (data) => {
    dashboardWindow?.webContents.send(IPC.ELBO_SCORE, data);
  });

  ws.on("training_step", (data) => {
    dashboardWindow?.webContents.send(IPC.TRAINING_STEP, data);
  });

  ws.on("label", (data) => {
    dashboardWindow?.webContents.send(IPC.LABEL, data);
  });

  ws.on("status", (data) => {
    dashboardWindow?.webContents.send(IPC.STATUS_UPDATE, data);
  });
}

// ── IPC handlers ─────────────────────────────────────────────

function setupIpc() {
  ipcMain.handle(IPC.CONTROL_TRAINING_START, () => api.startTraining());
  ipcMain.handle(IPC.CONTROL_TRAINING_STOP, () => api.stopTraining());
  ipcMain.handle(IPC.CONTROL_INFERENCE_START, () => api.startInference());
  ipcMain.handle(IPC.CONTROL_INFERENCE_STOP, () => api.stopInference());
  ipcMain.handle(IPC.REQUEST_PREDICTION, () => {
    ws.send("request_prediction");
  });
  ipcMain.handle(IPC.GET_STATUS, () => api.getStatus());
  ipcMain.handle(IPC.GET_SETTINGS, () => api.getSettings());
  ipcMain.handle(IPC.UPDATE_SETTINGS, (_e, data) => api.updateSettings(data));
  ipcMain.handle(IPC.GET_TRAINING_HISTORY, () => api.getTrainingHistory());

  // Overlay resize
  ipcMain.on("overlay:resize", (_e, height: number) => {
    resizeOverlay(height);
  });

  // Auto-update
  ipcMain.handle(IPC.UPDATE_INSTALL_NOW, () => installNow());
  ipcMain.handle(IPC.UPDATE_INSTALL_ON_QUIT, () => installOnNextLaunch());
  ipcMain.handle(IPC.UPDATE_DISMISS, () => dismissUpdate());
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

function launchApp(port: number) {
  createDashboard();
  createOverlay();
  setupWsForwarding();

  if (!isDev() && dashboardWindow) {
    initAutoUpdater(dashboardWindow);
  }

  startServer(port);

  waitForServer(`http://127.0.0.1:${port}/api/status`).then(async () => {
    // Push saved onboarding config to the server
    const config = onboarding.getConfig();
    if (config) {
      try {
        const { user_name, user_email, connectors: _connectors, ...serverConfig } = config as unknown as Record<string, unknown>;
        await api.updateSettings(serverConfig);
      } catch (err) {
        console.error("[onboarding] failed to push config to server:", err);
      }
    }
    ws.connect();
    dashboardWindow?.webContents.send(IPC.SERVER_READY);
  });

  globalShortcut.register("Control+H", toggleOverlay);
}

// ── App lifecycle ────────────────────────────────────────────

app.whenReady().then(async () => {
  app.dock?.show();
  setupIpc();
  setupConnectorIpc();
  initGoogleAuth();
  initOutlookAuth();

  // In packaged mode, check if bootstrap is needed
  if (!isDev() && !bootstrap.isReady()) {
    await runBootstrap();
  }

  // Onboarding: collect API keys and model on first launch
  if (!onboarding.isComplete()) {
    await onboarding.runOnboarding();
  }

  const port = await findFreePort();
  api.setServerUrl(`http://127.0.0.1:${port}`);
  launchApp(port);
});

app.on("before-quit", () => {
  isQuitting = true;
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    recorder.stopRecording();
    ws.disconnect();
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
