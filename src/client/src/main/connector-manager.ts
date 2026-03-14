/** Dashboard connector IPC handlers — manage connector status from the dashboard. */

import * as fs from "fs";
import { ipcMain } from "electron";
import { IPC } from "./ipc";
import { getConfig, ConnectorState } from "./onboarding";
import { isGoogleConnected, connectGoogle, disconnectGoogle } from "./gws-auth";
import { canReadNotifications } from "./notifications";
import { getDataDir } from "./paths";
import * as path from "path";

function saveConnectorState(connectors: ConnectorState): void {
  const configPath = path.join(getDataDir(), "powernap-config.json");
  try {
    const raw = fs.readFileSync(configPath, "utf-8");
    const config = JSON.parse(raw);
    config.connectors = connectors;
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), "utf-8");
  } catch {
    // Config file missing or corrupt — skip
  }
}

function saveGoogleConfigured(googleConfigured: { calendar: boolean; gmail: boolean }): void {
  const configPath = path.join(getDataDir(), "powernap-config.json");
  try {
    const raw = fs.readFileSync(configPath, "utf-8");
    const config = JSON.parse(raw);
    config.google_configured = googleConfigured;
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), "utf-8");
  } catch {
    // Config file missing or corrupt — skip
  }
}

export function setupConnectorIpc(): void {
  ipcMain.handle(IPC.CONNECTOR_STATUS, () => {
    const config = getConfig();
    const connectors = config?.connectors ?? {
      screen: false, calendar: false, gmail: false,
      notifications: false, filesystem: false,
    };
    const googleConnected = isGoogleConnected();
    return {
      screen: { enabled: connectors.screen, available: true, configured: true },
      calendar: { enabled: connectors.calendar, available: googleConnected, configured: config?.google_configured?.calendar ?? false },
      gmail: { enabled: connectors.gmail, available: googleConnected, configured: config?.google_configured?.gmail ?? false },
      notifications: { enabled: connectors.notifications, available: canReadNotifications(), configured: true },
      filesystem: { enabled: connectors.filesystem, available: true, configured: true },
    };
  });

  ipcMain.handle(IPC.CONNECTOR_CONNECT_GOOGLE, async (_e, scope?: string) => {
    const s = scope || "calendar,gmail";
    const ok = await connectGoogle(s);
    if (ok) {
      const cfg = getConfig();
      if (cfg) {
        const gc = cfg.google_configured ?? { calendar: false, gmail: false };
        if (s.includes("calendar")) gc.calendar = true;
        if (s.includes("gmail")) gc.gmail = true;
        saveGoogleConfigured(gc);
      }
    }
    return ok;
  });

  ipcMain.handle(IPC.CONNECTOR_DISCONNECT_GOOGLE, async () => {
    const ok = await disconnectGoogle();
    if (ok) {
      // Credentials removed — mark both Google services as disabled and unconfigured
      const config = getConfig();
      if (config?.connectors) {
        config.connectors.calendar = false;
        config.connectors.gmail = false;
        saveConnectorState(config.connectors);
      }
      saveGoogleConfigured({ calendar: false, gmail: false });
    }
    return ok;
  });

  ipcMain.handle(IPC.CONNECTOR_UPDATE, (_e, name: string, enabled: boolean) => {
    const config = getConfig();
    if (config && config.connectors) {
      (config.connectors as unknown as Record<string, boolean>)[name] = enabled;
      saveConnectorState(config.connectors);
    }
    return { ok: true };
  });
}
