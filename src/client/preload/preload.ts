/** Context bridge — exposes safe IPC methods to the renderer. */

import { contextBridge, ipcRenderer } from "electron";

// Cache server:ready so late-registering renderers (e.g. after Vite JS load)
// still get the payload even if the IPC fired before React mounted.
let serverReadyCache: { url: string } | null = null;
ipcRenderer.once("server:ready", (_e, data: { url: string }) => {
  serverReadyCache = data;
});

contextBridge.exposeInMainWorld("powernap", {
  // App lifecycle
  onServerReady: (cb: (data: { url: string }) => void) => {
    if (serverReadyCache) {
      cb(serverReadyCache);
    } else {
      ipcRenderer.once("server:ready", (_e, data) => cb(data));
    }
  },
  onPredictionRequested: (cb: () => void) =>
    ipcRenderer.on("prediction:requested", () => cb()),

  // Overlay
  onOverlayPrediction: (cb: (data: unknown) => void) =>
    ipcRenderer.on("overlay:prediction", (_e, data) => cb(data)),
  onOverlayWaiting: (cb: () => void) =>
    ipcRenderer.on("overlay:waiting", () => cb()),
  onOverlayFlushing: (cb: () => void) =>
    ipcRenderer.on("overlay:flushing", () => cb()),
  resizeOverlay: (height: number) =>
    ipcRenderer.send("overlay:resize", height),

  // Onboarding — screen permission (Electron-only) + completion signal
  checkScreenPermission: () =>
    ipcRenderer.invoke("onboarding:check-screen-permission"),
  openScreenSettings: () =>
    ipcRenderer.invoke("onboarding:open-screen-settings"),
  requestScreenPermission: () =>
    ipcRenderer.invoke("onboarding:request-screen-permission"),
  openNotifSettings: () =>
    ipcRenderer.invoke("onboarding:open-fda-settings"),
  onboardingComplete: () =>
    ipcRenderer.send("onboarding:complete"),

  // Connectors (OS-level permission checks only)
  openFdaSettings: (name?: string) => ipcRenderer.invoke("connector:open-fda-settings", name),
  getConnectorPermissionInfo: (name: string) => ipcRenderer.invoke("connector:get-permission-info", name),
  requestConnectorPermission: (name: string) => ipcRenderer.invoke("connector:request-permission", name),
  checkConnectorPermission: (name: string) => ipcRenderer.invoke("connector:check-permission", name),

  // Auto-update
  onUpdateDownloaded: (cb: (data: unknown) => void) =>
    ipcRenderer.on("update:downloaded", (_e, data) => cb(data)),
  onUpdateError: (cb: (msg: string) => void) =>
    ipcRenderer.on("update:error", (_e, msg) => cb(msg)),
  installNow: () => ipcRenderer.invoke("update:install-now"),
  installOnNextLaunch: () => ipcRenderer.invoke("update:install-on-quit"),
  dismissUpdate: () => ipcRenderer.invoke("update:dismiss"),
  checkForUpdates: () => ipcRenderer.invoke("update:check"),

  // Moments (Ta-Da)
  getMomentsTasks: () => ipcRenderer.invoke("moments:get-tasks"),
  getMomentsResults: () => ipcRenderer.invoke("moments:get-results"),
  getServerUrl: () => ipcRenderer.invoke("get:server-url"),
  onMomentCompleted: (cb: (data: unknown) => void) =>
    ipcRenderer.on("moment:completed", (_e, data) => cb(data)),

  // Bootstrap
  onBootstrapProgress: (cb: (msg: string, pct: number) => void) =>
    ipcRenderer.on("bootstrap:progress", (_e, msg, pct) => cb(msg, pct)),
  onBootstrapLog: (cb: (line: string) => void) =>
    ipcRenderer.on("bootstrap:log", (_e, line) => cb(line)),
  onBootstrapError: (cb: (errMsg: string) => void) =>
    ipcRenderer.on("bootstrap:error", (_e, errMsg) => cb(errMsg)),
  onBootstrapComplete: (cb: () => void) =>
    ipcRenderer.on("bootstrap:complete", () => cb()),
  retryBootstrap: () =>
    ipcRenderer.send("bootstrap:retry"),
});
