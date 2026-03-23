/** Dashboard connector IPC handlers — manage connector status from the dashboard. */

import { ipcMain, shell } from "electron";
import { IPC } from "./ipc";
import { getConfig, markGoogleConfigured } from "./onboarding";
import { isGoogleConnected, connectGoogle, disconnectGoogle } from "./google-auth";
import { isOutlookConnected, connectOutlook, disconnectOutlook } from "./outlook-auth";
import { connectorPermissions } from "./connector-permissions";
import * as api from "./api";

export function setupConnectorIpc(): void {
  ipcMain.handle(IPC.CONNECTOR_STATUS, async () => {
    const config = getConfig();
    const googleConnected = isGoogleConnected();
    const outlookConnected = isOutlookConnected();

    // Fetch enabled states from the server (authoritative source).
    // Fall back to all-enabled if the server isn't up yet.
    let serverStates: Record<string, { enabled: boolean; error?: string | null }> = {};
    try {
      serverStates = await api.getConnectors();
    } catch {
      // Server not ready yet — enabled state will be correct once it is
    }

    const enabled = (name: string) => serverStates[name]?.enabled ?? true;
    const error = (name: string) => serverStates[name]?.error ?? null;

    return {
      screen:           { enabled: enabled("screen"),           available: true,             configured: true,  error: error("screen") },
      calendar:         { enabled: enabled("calendar"),         available: googleConnected,  configured: config?.google_configured?.calendar ?? false, error: error("calendar") },
      gmail:            { enabled: enabled("gmail"),            available: googleConnected,  configured: config?.google_configured?.gmail ?? false,    error: error("gmail") },
      outlook_calendar: { enabled: enabled("outlook_calendar"), available: outlookConnected, configured: (config as any)?.outlook_configured?.calendar ?? false, error: error("outlook_calendar") },
      outlook_email:    { enabled: enabled("outlook_email"),    available: outlookConnected, configured: (config as any)?.outlook_configured?.email ?? false,    error: error("outlook_email") },
      notifications:    { enabled: enabled("notifications"),    available: true,             configured: true,  error: error("notifications") },
      filesystem:       { enabled: enabled("filesystem"),       available: true,             configured: true,  error: error("filesystem") },
    };
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
        await Promise.all([
          api.updateConnector("calendar", false),
          api.updateConnector("email", false),
        ]);
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
        await Promise.all([
          api.updateConnector("outlook_calendar", false),
          api.updateConnector("outlook_email", false),
        ]);
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

  ipcMain.handle(IPC.CONNECTOR_UPDATE, async (_e, name: string, enabled: boolean) => {
    try {
      await api.updateConnector(name, enabled);
    } catch {
      // Server may not be ready yet; state is persisted server-side so it
      // will be correct on next launch once the server starts.
    }
    return { ok: true };
  });
}
