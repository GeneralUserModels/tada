/** Context bridge — exposes safe IPC methods to the renderer. */

import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("powernap", {
  // App lifecycle
  onServerReady: (cb: (data: { url: string }) => void) =>
    ipcRenderer.once("server:ready", (_e, data) => cb(data)),
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
  connectGoogle: (scope?: string) => ipcRenderer.invoke("onboarding:connect-google", scope),
  connectOutlook: () => ipcRenderer.invoke("onboarding:connect-outlook"),
  checkNotifications: () => ipcRenderer.invoke("onboarding:check-notifications"),
  checkFilesystem: () => ipcRenderer.invoke("onboarding:check-filesystem"),
  openNotifSettings: () => ipcRenderer.invoke("onboarding:open-fda-settings"),

  // Connectors (OAuth and OS-level only — data fetching goes direct to Python)
  getConnectorStatus: () => ipcRenderer.invoke("connector:status"),
  connectorConnectGoogle: (scope?: string) => ipcRenderer.invoke("connector:connect-google", scope),
  connectorDisconnectGoogle: () => ipcRenderer.invoke("connector:disconnect-google"),
  connectorConnectOutlook: () => ipcRenderer.invoke("connector:connect-outlook"),
  connectorDisconnectOutlook: () => ipcRenderer.invoke("connector:disconnect-outlook"),
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
