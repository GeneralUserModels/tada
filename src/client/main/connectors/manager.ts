/** Dashboard connector IPC handlers — manage connector status from the dashboard. */

import { ipcMain, shell } from "electron";
import { IPC } from "../ipc";
import { getConfig, markGoogleConfigured } from "../features/onboarding";
import { isGoogleConnected, connectGoogle, disconnectGoogle } from "../auth/google";
import { isOutlookConnected, connectOutlook, disconnectOutlook } from "../auth/outlook";
import { connectorPermissions } from "./permissions";
import * as api from "../api";

export function setupConnectorIpc(): void {
  ipcMain.handle(IPC.CONNECTOR_STATUS, async () => {
    const config = getConfig();
    const googleConnected = isGoogleConnected();
    const outlookConnected = isOutlookConnected();

    // Fetch enabled states from the server (authoritative source).
    // Fall back to all-enabled if the server isn't up yet.
    let serverStates: Record<string, { enabled: boolean; error?: string | null; requires_auth?: string | null }> = {};
    try {
      serverStates = await api.getConnectors();
    } catch {
      // Server not ready yet — enabled state will be correct once it is
    }

    const authAvailable = (ra: string | null | undefined) => {
      if (ra === "google") return googleConnected;
      if (ra === "outlook") return outlookConnected;
      return true;
    };
    const authConfigured = (name: string, ra: string | null | undefined) => {
      if (ra === "google") {
        const gc = config?.google_configured as Record<string, boolean> | undefined;
        return gc?.[name] ?? false;
      }
      if (ra === "outlook") {
        const key = name.replace("outlook_", "") as "calendar" | "email";
        return config?.outlook_configured?.[key] ?? false;
      }
      return true;
    };

    return Object.fromEntries(
      Object.entries(serverStates).map(([name, s]) => [
        name,
        {
          enabled: s.enabled,
          available: authAvailable(s.requires_auth),
          configured: authConfigured(name, s.requires_auth),
          error: s.error ?? null,
          requires_auth: s.requires_auth ?? null,
        },
      ])
    );
  });

  ipcMain.handle(IPC.CONNECTOR_CONNECT_GOOGLE, async (_e, scope?: string) => {
    const s = scope || "calendar,gmail";
    const ok = await connectGoogle(s);
    if (ok) {
      const scopes = s.split(",");
      markGoogleConfigured(
        scopes.includes("calendar") ? true : undefined,
        scopes.includes("gmail") ? true : undefined,
      );
    }
    return ok;
  });

  ipcMain.handle(IPC.CONNECTOR_DISCONNECT_GOOGLE, async () => {
    const ok = await disconnectGoogle();
    if (ok) {
      try {
        const connectors = await api.getConnectors();
        const googleConnectors = Object.entries(connectors)
          .filter(([, v]) => v.requires_auth === "google")
          .map(([name]) => name);
        await Promise.all(googleConnectors.map(name => api.updateConnector(name, false)));
      } catch { /* server may not be ready */ }
    }
    return ok;
  });

  ipcMain.handle(IPC.CONNECTOR_CONNECT_OUTLOOK, async () => {
    return connectOutlook();
  });

  ipcMain.handle(IPC.CONNECTOR_DISCONNECT_OUTLOOK, async () => {
    const ok = await disconnectOutlook();
    if (ok) {
      try {
        const connectors = await api.getConnectors();
        const outlookConnectors = Object.entries(connectors)
          .filter(([, v]) => v.requires_auth === "outlook")
          .map(([name]) => name);
        await Promise.all(outlookConnectors.map(name => api.updateConnector(name, false)));
      } catch { /* server may not be ready */ }
    }
    return ok;
  });

  ipcMain.handle(IPC.CONNECTOR_OPEN_FDA_SETTINGS, (_e, name?: string) => {
    const url = (name && connectorPermissions[name]?.fixUrl)
      ?? "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles";
    shell.openExternal(url);
  });

  ipcMain.handle(IPC.CONNECTOR_GET_PERMISSION_INFO, (_e, name: string) => {
    const desc = connectorPermissions[name];
    if (!desc) return null;
    return {
      title: desc.title,
      body: desc.body,
      steps: desc.steps,
      fixUrl: desc.fixUrl,
      hasRequest: !!desc.request,
    };
  });

  ipcMain.handle(IPC.CONNECTOR_REQUEST_PERMISSION, async (_e, name: string) => {
    const desc = connectorPermissions[name];
    if (!desc?.request) return desc?.check() ?? true;
    return desc.request();
  });

}
