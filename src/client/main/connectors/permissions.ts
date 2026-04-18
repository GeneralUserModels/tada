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
  check: () => boolean | Promise<boolean>;
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
  check: async () => {
    const status = systemPreferences.getMediaAccessStatus("screen");
    if (status !== "granted") return false;
    // systemPreferences can report "granted" incorrectly (dev builds inherit
    // terminal permissions, macOS Sequoia API changes). Verify with a real capture.
    try {
      const sources = await desktopCapturer.getSources({
        types: ["screen"],
        thumbnailSize: { width: 1, height: 1 },
      });
      if (!sources.length) return false;
      const bmp = sources[0].thumbnail.toBitmap();
      if (bmp.length === 0) return false;
      // All-zero alpha channel = blank capture = no real permission
      for (let i = 3; i < bmp.length; i += 4) {
        if (bmp[i] !== 0) return true;
      }
      return false;
    } catch {
      return false;
    }
  },

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
  body: "Tada needs Screen Recording permission to observe your workflow.",
  steps: [
    "Open System Settings → Privacy & Security → Screen Recording",
    'Toggle on "Tada"',
    "Restart Tada if prompted",
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

  request: async () => {
    // No programmatic dialog for FDA — open Settings directly.
    shell.openExternal(
      "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    );
    return false;
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
  title: "Full Disk Access Required",
  body: "Tada needs Full Disk Access to read notifications, files, and browser data.",
  steps: [
    "Open System Settings → Privacy & Security → Full Disk Access",
    'Click the "+" button',
    'Select "Tada"',
    "Toggle the switch on",
  ],
};

// ── Accessibility ────────────────────────────────────────────────────────────

const accessibilityPermission: PermissionDescriptor = {
  check: () => systemPreferences.isTrustedAccessibilityClient(false),

  request: async () => {
    // Prompt the native macOS dialog
    const trusted = systemPreferences.isTrustedAccessibilityClient(true);
    if (!trusted) {
      shell.openExternal(
        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
      );
    }
    return trusted;
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
  title: "Accessibility Required",
  body: "Tada needs Accessibility permission for Tab autocomplete (Tabracadabra).",
  steps: [
    "Open System Settings → Privacy & Security → Accessibility",
    'Toggle on "Tada" switch on (or the terminal, if you\'re in developer mode)',
  ],
};

// ── Browser Cookies (Chrome — requires Full Disk Access) ─────────────────────

const CHROME_COOKIES = path.join(
  os.homedir(),
  "Library", "Application Support",
  "Google", "Chrome", "Default", "Cookies",
);

const browserCookiesPermission: PermissionDescriptor = {
  check: () => {
    try {
      fs.accessSync(CHROME_COOKIES, fs.constants.R_OK);
      return true;
    } catch {
      return false;
    }
  },

  request: async () => {
    shell.openExternal(
      "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
    );
    return false;
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
  title: "Full Disk Access Required",
  body: "Tada needs Full Disk Access to read Chrome cookies for web browsing.",
  steps: [
    "Open System Settings → Privacy & Security → Full Disk Access",
    'Click the "+" button',
    'Select "Tada"',
    "Toggle the switch on",
  ],
};

// ── Registry ──────────────────────────────────────────────────────────────────

export const connectorPermissions: Partial<Record<string, PermissionDescriptor>> = {
  screen: screenPermission,
  notifications: notificationsPermission,
  accessibility: accessibilityPermission,
  browser_cookies: browserCookiesPermission,
};

/** Returns true if the named connector either has no permission requirement or passes its check. */
export async function canUseConnector(name: string): Promise<boolean> {
  return (await connectorPermissions[name]?.check()) ?? true;
}
