/** Main process: window management, global shortcuts, IPC handlers, child processes. */

import {
  app,
  BrowserWindow,
  globalShortcut,
  ipcMain,
  screen,
} from "electron";
import * as path from "path";
import { IPC } from "./ipc";
import * as api from "./api";
import * as ws from "./ws";
import * as recorder from "./recorder";

let dashboardWindow: BrowserWindow | null = null;
let overlayWindow: BrowserWindow | null = null;
let overlayVisible = false;

// ── Window creation ──────────────────────────────────────────

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

  dashboardWindow.on("closed", () => {
    dashboardWindow = null;
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
  ipcMain.handle(IPC.CONTROL_RECORDING_START, async () => {
    recorder.startRecording();
    return api.startRecording();
  });
  ipcMain.handle(IPC.CONTROL_RECORDING_STOP, async () => {
    recorder.stopRecording();
    return api.stopRecording();
  });
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
}

// ── App lifecycle ────────────────────────────────────────────

app.whenReady().then(() => {
  createDashboard();
  createOverlay();
  setupIpc();
  setupWsForwarding();
  ws.connect();

  // Global shortcuts
  globalShortcut.register("Control+H", toggleOverlay);
  globalShortcut.register("Control+G", () => {
    // Sleepwalk toggle — forward to overlay
    overlayWindow?.webContents.send(IPC.OVERLAY_SLEEPWALK);
  });
});

app.on("window-all-closed", () => {
  recorder.stopRecording();
  ws.disconnect();
  app.quit();
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
});
