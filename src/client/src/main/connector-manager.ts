/** Dashboard connector IPC handlers — manage connector status from the dashboard. */

import { ipcMain } from "electron";
import { IPC } from "./ipc";
import { getConfig } from "./onboarding";
import { isGoogleConnected, connectGoogle, disconnectGoogle } from "./google-auth";
import { isOutlookConnected, connectOutlook, disconnectOutlook } from "./outlook-auth";
import { canReadNotifications } from "./notifications";
import * as api from "./api";

export function setupConnectorIpc(): void {
  ipcMain.handle(IPC.CONNECTOR_STATUS, async () => {
    const config = getConfig();
    const googleConnected = isGoogleConnected();
    const outlookConnected = isOutlookConnected();

    // Fetch enabled states from the server (authoritative source).
    // Fall back to all-enabled if the server isn't up yet.
    let serverStates: Record<string, { enabled: boolean }> = {};
    try {
      serverStates = await api.getConnectors();
    } catch {
      // Server not ready yet — enabled state will be correct once it is
    }

    const enabled = (name: string) => serverStates[name]?.enabled ?? true;

    return {
      screen:           { enabled: enabled("screen"),           available: true,              configured: true },
      calendar:         { enabled: enabled("calendar"),         available: googleConnected,   configured: config?.google_configured?.calendar ?? false },
      gmail:            { enabled: enabled("email"),            available: googleConnected,   configured: config?.google_configured?.gmail ?? false },
      outlook_calendar: { enabled: enabled("outlook_calendar"), available: outlookConnected,  configured: (config as any)?.outlook_configured?.calendar ?? false },
      outlook_email:    { enabled: enabled("outlook_email"),    available: outlookConnected,  configured: (config as any)?.outlook_configured?.email ?? false },
      notifications:    { enabled: enabled("notifications"),    available: canReadNotifications(), configured: true },
      filesystem:       { enabled: enabled("filesystem"),       available: true,              configured: true },
    };
  });

  ipcMain.handle(IPC.CONNECTOR_CONNECT_GOOGLE, async (_e, scope?: string) => {
    const s = scope || "calendar,gmail";
    return connectGoogle(s);
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
