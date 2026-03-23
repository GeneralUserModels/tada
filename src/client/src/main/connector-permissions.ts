/**
 * Permission descriptors for connectors that require OS-level access grants.
 *
 * Each descriptor is the single source of truth for:
 *   - check()    — whether the app currently has the required permission
 *   - request()  — optional: programmatically trigger the native OS dialog
 *                  (supported for screen recording; not available for FDA)
 *   - fixUrl     — deep-link to the relevant System Settings pane
 *   - title / body / steps — content for the shared permission modal
 *
 * Adding a new connector permission = add one entry here. The modal, toggle
 * interception, and onboarding flow all pick it up automatically.
 */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import { desktopCapturer, shell, systemPreferences } from "electron";

export interface PermissionDescriptor {
  /** Returns true if the app currently has the required OS permission. */
  check: () => boolean;
  /**
   * Optional: programmatically trigger the native OS permission dialog.
   * Returns true if permission was granted after the request.
   * When present, the modal fires this immediately on open before falling back
   * to the "Open Settings" walkthrough.
   */
  request?: () => Promise<boolean>;
  /** Deep-link URL to the relevant System Settings pane. */
  fixUrl: string;
  /** Short title for the permission modal. */
  title: string;
  /** One-sentence explanation shown in the modal. */
  body: string;
  /** Ordered steps to walk the user through granting access. */
  steps: string[];
}

// ── Screen Recording ──────────────────────────────────────────────────────────

const screenPermission: PermissionDescriptor = {
  check: () => systemPreferences.getMediaAccessStatus("screen") === "granted",

  request: async () => {
    // Trigger the macOS native permission dialog by attempting a capture.
    try {
      await desktopCapturer.getSources({
        types: ["screen"],
        thumbnailSize: { width: 320, height: 240 },
      });
    } catch { /* permission denied — falls through to check below */ }

    const status = systemPreferences.getMediaAccessStatus("screen");
    if (status !== "granted") {
      // On macOS Sequoia+ the dialog doesn't appear; open Settings directly.
      shell.openExternal(
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
      );
    }
    return status === "granted";
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
  title: "Screen Recording Required",
  body: "PowerNap needs Screen Recording permission to observe your workflow.",
  steps: [
    "Open System Settings → Privacy & Security → Screen Recording",
    'Toggle on "Electron" (dev) or "PowerNap" (production)',
    "Restart PowerNap if prompted",
  ],
};

// ── Notifications (Full Disk Access) ──────────────────────────────────────────

const NOTIFICATIONS_DB = path.join(
  os.homedir(),
  "Library", "Group Containers",
  "group.com.apple.usernoted", "db2", "db",
);

const notificationsPermission: PermissionDescriptor = {
  check: () => {
    try {
      fs.accessSync(NOTIFICATIONS_DB, fs.constants.R_OK);
      return true;
    } catch {
      return false;
    }
  },

  // No request() — Full Disk Access has no programmatic dialog API.

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
  title: "Full Disk Access Required",
  body: "PowerNap needs Full Disk Access to read your macOS notification history.",
  steps: [
    "Open System Settings → Privacy & Security → Full Disk Access",
    'Click the "+" button',
    'Select "Electron" (dev) or "PowerNap" (production)',
    "Toggle the switch on",
  ],
};

// ── Registry ──────────────────────────────────────────────────────────────────

export const connectorPermissions: Partial<Record<string, PermissionDescriptor>> = {
  screen: screenPermission,
  notifications: notificationsPermission,
};

/** Returns true if the named connector either has no permission requirement or passes its check. */
export function canUseConnector(name: string): boolean {
  return connectorPermissions[name]?.check() ?? true;
}
