/** Dashboard connector IPC handlers — OS-level permission checks only.
 *
 * OAuth connect/disconnect and status are now handled by the Python server
 * (POST/DELETE /api/auth/google|outlook, GET /api/connectors). The renderer
 * calls those endpoints directly instead of going through IPC.
 */

import { ipcMain, shell } from "electron";
import { IPC } from "../ipc";
import { connectorPermissions, canUseConnector } from "./permissions";

export function setupConnectorIpc(): void {
  ipcMain.handle(IPC.CONNECTOR_OPEN_FDA_SETTINGS, async (_e, name?: string) => {
    // Call request() first so permissions that need to trigger TCC registration
    // (Full Disk Access) do an actual open() on the protected path — without
    // this, the app never appears in the Full Disk Access list in System
    // Settings and the user has nothing to toggle.
    const desc = name ? connectorPermissions[name] : undefined;
    if (desc?.request) {
      try { await desc.request(); } catch { /* fall through to Settings */ }
    }
    const url = desc?.fixUrl
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
    if (!desc?.request) return (await desc?.check()) ?? true;
    return desc.request();
  });

  ipcMain.handle(IPC.CONNECTOR_CHECK_PERMISSION, async (_e, name: string) => {
    return canUseConnector(name);
  });
}
