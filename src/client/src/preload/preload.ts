/** Context bridge — exposes safe IPC methods to the renderer. */

import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("powernap", {
  // Control
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
  getLabelHistory: () => ipcRenderer.invoke("get:label:history"),

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
  // Overlay resize (renderer -> main)
  resizeOverlay: (height: number) =>
    ipcRenderer.send("overlay:resize", height),

  // Onboarding
  googleLogin: () => ipcRenderer.invoke("onboarding:google-login"),
  submitOnboarding: (data: Record<string, unknown>) =>
    ipcRenderer.invoke("onboarding:submit", data),
  checkScreenPermission: () =>
    ipcRenderer.invoke("onboarding:check-screen-permission"),
  openScreenSettings: () =>
    ipcRenderer.invoke("onboarding:open-screen-settings"),
  requestScreenPermission: () =>
    ipcRenderer.invoke("onboarding:request-screen-permission"),

  // Onboarding connectors
  connectGoogle: (scope?: string) => ipcRenderer.invoke("onboarding:connect-google", scope),
  connectOutlook: () => ipcRenderer.invoke("onboarding:connect-outlook"),
  checkNotifications: () => ipcRenderer.invoke("onboarding:check-notifications"),
  checkFilesystem: () => ipcRenderer.invoke("onboarding:check-filesystem"),
  openNotifSettings: () => ipcRenderer.invoke("onboarding:open-fda-settings"),

  // Dashboard connectors
  getConnectorStatus: () => ipcRenderer.invoke("connector:status"),
  connectorConnectGoogle: (scope?: string) => ipcRenderer.invoke("connector:connect-google", scope),
  connectorDisconnectGoogle: () => ipcRenderer.invoke("connector:disconnect-google"),
  connectorConnectOutlook: () => ipcRenderer.invoke("connector:connect-outlook"),
  connectorDisconnectOutlook: () => ipcRenderer.invoke("connector:disconnect-outlook"),
  updateConnector: (name: string, enabled: boolean) =>
    ipcRenderer.invoke("connector:update", name, enabled),
  openFdaSettings: (name?: string) => ipcRenderer.invoke("connector:open-fda-settings", name),
  onConnectorUpdate: (cb: (data: unknown) => void) =>
    ipcRenderer.on("connector:status-update", (_e, data) => cb(data)),
  getConnectorPermissionInfo: (name: string) => ipcRenderer.invoke("connector:get-permission-info", name),
  requestConnectorPermission: (name: string) => ipcRenderer.invoke("connector:request-permission", name),

  // Auto-update
  onUpdateDownloaded: (cb: (data: unknown) => void) =>
    ipcRenderer.on("update:downloaded", (_e, data) => cb(data)),
  onUpdateError: (cb: (msg: string) => void) =>
    ipcRenderer.on("update:error", (_e, msg) => cb(msg)),
  installNow: () => ipcRenderer.invoke("update:install-now"),
  installOnNextLaunch: () => ipcRenderer.invoke("update:install-on-quit"),
  dismissUpdate: () => ipcRenderer.invoke("update:dismiss"),
  checkForUpdates: () => ipcRenderer.invoke("update:check"),

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
