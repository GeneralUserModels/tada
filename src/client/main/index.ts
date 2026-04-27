/** Main process: window management, IPC handlers, child processes. */

import {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  shell,
} from "electron";
import * as fs from "fs";
import * as path from "path";
import { spawn, ChildProcess } from "child_process";
import { IPC } from "./ipc";
import * as api from "./api";
import * as sse from "./sse";
import { isDev, getDataDir, getPythonPath, getLogDir, getPythonSrcDir, getGoogleTokenPath, getOutlookTokenPath, getPlaywrightBrowsersDir } from "./paths";
import * as bootstrap from "./features/bootstrap";
import { runOnboarding, getOnboardingWindow } from "./features/onboarding";
import { setupConnectorIpc } from "./connectors/manager";
import { initUpdateChecker, checkForUpdates, installUpdate } from "./features/updater";
import { pendingSteps, type OnboardingState } from "../shared/onboardingSteps";

let serverProc: ChildProcess | null = null;

// ── File logging ─────────────────────────────────────────────
// When launched from Finder/Spotlight, Electron's stdout/stderr go nowhere
// visible — silent failures (missing API keys, server crashes) are then
// invisible to users. Mirror everything to a file in the data dir so we have
// something to point users at.

let logStream: fs.WriteStream | null = null;
let serverReady = false;

function initFileLogging(): void {
  const dir = getLogDir();
  fs.mkdirSync(dir, { recursive: true });
  const logPath = path.join(dir, "electron.log");
  logStream = fs.createWriteStream(logPath, { flags: "a" });
  logStream.write(`\n=== launch ${new Date().toISOString()} pid=${process.pid} packaged=${!isDev()} ===\n`);

  const tee = (orig: NodeJS.WriteStream["write"], stream: NodeJS.WriteStream) =>
    ((chunk: string | Uint8Array, ...rest: unknown[]) => {
      try { logStream?.write(chunk as Buffer | string); } catch {}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return (orig as any).call(stream, chunk, ...rest);
    }) as NodeJS.WriteStream["write"];
  process.stdout.write = tee(process.stdout.write.bind(process.stdout), process.stdout);
  process.stderr.write = tee(process.stderr.write.bind(process.stderr), process.stderr);

  process.on("uncaughtException", (err) => {
    console.error("[uncaughtException]", err?.stack ?? err);
  });
  process.on("unhandledRejection", (reason) => {
    console.error("[unhandledRejection]", reason);
  });
}

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

function readOnboardingState(): { needed: boolean; mode: "first" | "returning" } {
  let cfg: Record<string, unknown> = {};
  try {
    const configPath = path.join(getDataDir(), "tada-config.json");
    cfg = JSON.parse(fs.readFileSync(configPath, "utf-8"));
  } catch {
    return { needed: true, mode: "first" };
  }
  // Match the server's definition of "signed in" (see /api/auth/google/user):
  // having google_user_email persisted is the source of truth, not the on-disk
  // token. Otherwise the main process disagrees with the renderer about what's
  // pending — the window opens, the renderer immediately decides nothing is
  // pending, and we flash the empty "What's New" loading shell on every launch.
  const googleEmail = typeof cfg.google_user_email === "string" ? cfg.google_user_email as string : "";
  const state: OnboardingState = {
    seenSteps: Array.isArray(cfg.onboarding_steps_seen) ? cfg.onboarding_steps_seen as string[] : [],
    featureFlags: (cfg.feature_flags as Record<string, boolean> | undefined),
    googleConnected: googleEmail.length > 0 || fs.existsSync(getGoogleTokenPath()),
    enabledConnectors: Array.isArray(cfg.enabled_connectors) ? cfg.enabled_connectors as string[] : [],
    hasLlmApiKey: typeof cfg.default_llm_api_key === "string" && cfg.default_llm_api_key.length > 0,
    onboardingComplete: cfg.onboarding_complete === true,
    // The main process can't probe live service status; treat onboardingComplete
    // as a good proxy here (the lifespan auto-starts services on next boot).
    // The renderer re-evaluates with a real /api/services/status call.
    servicesReady: cfg.onboarding_complete === true,
  };
  return {
    needed: pendingSteps(state).length > 0,
    mode: state.onboardingComplete ? "returning" : "first",
  };
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
    // Packaged mode: use venv python directly.
    // Finder/Spotlight launches inherit a minimal PATH (`/usr/bin:/bin:/...`),
    // which doesn't contain the bundled `rg` we drop into the data dir during
    // bootstrap. sandbox_runtime resolves `rg` via shutil.which, so without
    // this prepend it raises "Sandbox dependencies not available" the first
    // time the chat agent tries to start. Terminal launches happen to work
    // only because the user's shell PATH usually has Homebrew's `rg`.
    const dataDir = getDataDir();
    const existingPath = process.env.PATH ?? "/usr/bin:/bin:/usr/sbin:/sbin";
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
      cwd: dataDir,
      env: {
        ...process.env,
        PATH: `${dataDir}:${existingPath}`,
        PYTHONPATH: pythonSrcDir,
        TADA_CONFIG_PATH: configPath,
        // Never write .pyc files into the signed .app bundle — that breaks
        // the codesign seal and causes macOS TCC to silently refuse to list
        // the app in Privacy & Security panes. Redirect bytecode cache to
        // the writable data dir instead.
        PYTHONPYCACHEPREFIX: path.join(getDataDir(), "pycache"),
        PYTHONDONTWRITEBYTECODE: "1",
        // Pin Playwright to the app-local browsers dir installed in
        // bootstrap. Must match the path used at install time.
        PLAYWRIGHT_BROWSERS_PATH: getPlaywrightBrowsersDir(),
      },
    });
  }

  serverProc.stdout?.on("data", (chunk: Buffer) => {
    process.stdout.write(`[server] ${chunk}`);
  });
  serverProc.stderr?.on("data", (chunk: Buffer) => {
    process.stderr.write(`[server] ${chunk}`);
  });
  serverProc.on("exit", (code, signal) => {
    console.log(`[server] exited with code ${code} signal ${signal}`);
    const wasUnexpected = !isQuitting && !serverReady;
    serverProc = null;
    if (wasUnexpected) {
      const logPath = path.join(getLogDir(), "electron.log");
      dialog.showErrorBox(
        "Tada server failed to start",
        `The Python server exited with code ${code} before becoming ready.\n\n` +
        `Logs: ${logPath}`,
      );
    }
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

function createDashboard({ show = true }: { show?: boolean } = {}) {
  dashboardWindow = new BrowserWindow({
    width: 900,
    height: 700,
    show,
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

  dashboardWindow.webContents.on("context-menu", (_event, params) => {
    const items: Electron.MenuItemConstructorOptions[] = [];
    if (params.selectionText) {
      items.push({ label: "Copy", role: "copy" });
    }
    if (params.isEditable) {
      items.push(
        { label: "Cut", role: "cut" },
        { label: "Paste", role: "paste" },
      );
    }
    if (params.selectionText || params.isEditable) {
      items.push({ type: "separator" });
    }
    items.push({ label: "Select All", role: "selectAll" });
    Menu.buildFromTemplate(items).popup();
  });

  dashboardWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      dashboardWindow?.hide();
    }
  });
}

// ── SSE event forwarding ─────────────────────────────────────

function setupSseForwarding() {
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

  // Update check
  ipcMain.handle(IPC.UPDATE_CHECK, () => checkForUpdates());
  ipcMain.on(IPC.UPDATE_INSTALL, () => installUpdate());

  // Open URLs in the OS default browser
  ipcMain.handle(IPC.OPEN_EXTERNAL_URL, (_e, url: string) => {
    if (typeof url !== "string" || !url.trim()) return false;
    shell.openExternal(url);
    return true;
  });
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
  initFileLogging();
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

  const { needed: showOnboarding, mode: onboardingMode } = readOnboardingState();

  // Show the dashboard immediately for returning users so they see a
  // loading state while the server starts. For first-launch, keep it
  // hidden until onboarding finishes.
  createDashboard({ show: !showOnboarding });
  setupSseForwarding();

  const serverReadyPromise = waitForServer(`${api.getServerUrl()}/api/status`).then(() => {
    serverReady = true;
  });

  if (showOnboarding) {
    // Open onboarding immediately so there's no windowless gap after
    // setup closes. The server boots in parallel; onboarding defers
    // its SERVER_READY IPC until the promise resolves.
    await runOnboarding(serverReadyPromise, onboardingMode);
    dashboardWindow?.show();
  } else {
    await serverReadyPromise;
  }

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
}).catch((err: unknown) => {
  const message = err instanceof Error ? err.stack ?? err.message : String(err);
  console.error("[startup] fatal error", message);
  dialog.showErrorBox("Tada failed to start", message);
  app.quit();
});

app.on("before-quit", () => {
  isQuitting = true;
  stopServer();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    sse.disconnect();
    stopServer();
    app.quit();
  }
});

app.on("activate", () => {
  const onboarding = getOnboardingWindow();
  if (onboarding) {
    onboarding.show();
    onboarding.focus();
  } else if (dashboardWindow) {
    dashboardWindow.show();
  }
});

