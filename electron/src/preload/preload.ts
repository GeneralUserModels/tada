/** Context bridge — exposes safe IPC methods to the renderer. */

import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("powernap", {
  // Control
  startRecording: () => ipcRenderer.invoke("control:recording:start"),
  stopRecording: () => ipcRenderer.invoke("control:recording:stop"),
  startTraining: () => ipcRenderer.invoke("control:training:start"),
  stopTraining: () => ipcRenderer.invoke("control:training:stop"),
  startInference: () => ipcRenderer.invoke("control:inference:start"),
  stopInference: () => ipcRenderer.invoke("control:inference:stop"),
  requestPrediction: () => ipcRenderer.invoke("request:prediction"),

  // Status / Settings
  getStatus: () => ipcRenderer.invoke("get:status"),
  getSettings: () => ipcRenderer.invoke("get:settings"),
  updateSettings: (data: Record<string, unknown>) =>
    ipcRenderer.invoke("update:settings", data),
  getTrainingHistory: () => ipcRenderer.invoke("get:training:history"),

  // Event listeners (main -> renderer)
  onServerReady: (cb: () => void) =>
    ipcRenderer.once("server:ready", () => cb()),
  onStatusUpdate: (cb: (data: unknown) => void) =>
    ipcRenderer.on("status:update", (_e, data) => cb(data)),
  onPrediction: (cb: (data: unknown) => void) =>
    ipcRenderer.on("prediction", (_e, data) => cb(data)),
  onScore: (cb: (data: unknown) => void) =>
    ipcRenderer.on("score", (_e, data) => cb(data)),
  onElboScore: (cb: (data: unknown) => void) =>
    ipcRenderer.on("elbo:score", (_e, data) => cb(data)),
  onTrainingStep: (cb: (data: unknown) => void) =>
    ipcRenderer.on("training:step", (_e, data) => cb(data)),
  onLabel: (cb: (data: unknown) => void) =>
    ipcRenderer.on("label", (_e, data) => cb(data)),

  onPredictionRequested: (cb: () => void) =>
    ipcRenderer.on("prediction:requested", () => cb()),

  // Overlay-specific
  onOverlayPrediction: (cb: (data: unknown) => void) =>
    ipcRenderer.on("overlay:prediction", (_e, data) => cb(data)),
  onOverlayWaiting: (cb: () => void) =>
    ipcRenderer.on("overlay:waiting", () => cb()),
  onOverlayFlushing: (cb: () => void) =>
    ipcRenderer.on("overlay:flushing", () => cb()),
  onOverlaySleepwalk: (cb: () => void) =>
    ipcRenderer.on("overlay:sleepwalk", () => cb()),

  // Overlay resize (renderer -> main)
  resizeOverlay: (height: number) =>
    ipcRenderer.send("overlay:resize", height),
});
