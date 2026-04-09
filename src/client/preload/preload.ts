/** Context bridge — exposes safe IPC methods to the renderer. */

import { contextBridge, ipcRenderer } from "electron";

// Cache one-shot IPCs so late-registering renderers (e.g. after Vite JS load)
// still get the payload even if the IPC fired before React mounted.
let serverReadyCache: { url: string } | null = null;
ipcRenderer.once("server:ready", (_e, data: { url: string }) => {
  serverReadyCache = data;
});

let updateAvailableCache: { version: string } | null = null;
ipcRenderer.on("update:available", (_e, data: { version: string }) => {
  updateAvailableCache = data;
});

contextBridge.exposeInMainWorld("tada", {
  // App lifecycle
  onServerReady: (cb: (data: { url: string }) => void) => {
    if (serverReadyCache) {
      cb(serverReadyCache);
    } else {
      ipcRenderer.once("server:ready", (_e, data) => cb(data));
    }
  },
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

  // Update check
  onUpdateAvailable: (cb: (data: { version: string }) => void) => {
    if (updateAvailableCache) cb(updateAvailableCache);
    ipcRenderer.on("update:available", (_e, data) => cb(data));
  },
  dismissUpdate: () => ipcRenderer.send("update:dismiss"),
  checkForUpdates: () => ipcRenderer.invoke("update:check"),

  // External links
  openExternalUrl: (url: string) => ipcRenderer.invoke("external:open-url", url),

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
