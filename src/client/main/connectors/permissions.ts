/**
 * Permission descriptors for connectors that require OS-level access grants.
 *
 * Each descriptor is the single source of truth for:
 *   - check()    — whether the app currently has the required permission
 *   - request()  — optional: programmatically trigger the native OS dialog
 *                  (supported for screen recording, folders, microphone;
 *                  not available for FDA or Accessibility — those open Settings)
 *   - fixUrl     — deep-link to the relevant System Settings pane
 *   - title / body / steps — content for the shared permission modal
 *
 * Adding a new connector permission = add one entry here. The modal, toggle
 * interception, and onboarding flow all pick it up automatically.
 *
 * Native prompts are routed through `node-mac-permissions`, which wraps the
 * underlying AppKit/AVFoundation/CoreGraphics APIs (e.g. CGRequestScreenCapture-
 * Access, FileProvider folder prompts) rather than going through Chromium's
 * `getDisplayMedia` / `askForMediaAccess` shims.
 */

import { shell, systemPreferences } from "electron";

// node-mac-permissions is a native module; load lazily so non-macOS runs
// (dev on linux/windows, or a broken rebuild) don't take the whole app down.
type MacAuthType =
  | "screen"
  | "full-disk-access"
  | "microphone"
  | "accessibility"
  | "camera"
  | "input-monitoring"
  | "notifications";
type MacPermissions = {
  getAuthStatus: (t: MacAuthType) => string;
  askForScreenCaptureAccess: (openPrefs?: boolean) => void;
  askForFoldersAccess: (folder: "desktop" | "documents" | "downloads") => Promise<string>;
  askForFullDiskAccess: () => void;
  askForMicrophoneAccess: () => Promise<string>;
  askForAccessibilityAccess: () => void;
};

let _mac: MacPermissions | null | undefined;
function mac(): MacPermissions | null {
  if (_mac !== undefined) return _mac;
  try {
    _mac = process.platform === "darwin"
      ? (require("node-mac-permissions") as MacPermissions)
      : null;
  } catch (err) {
    console.warn("[permissions] node-mac-permissions unavailable:", err);
    _mac = null;
  }
  return _mac;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

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
  check: () => mac()?.getAuthStatus("screen") === "authorized",

  request: async () => {
    // askForScreenCaptureAccess wraps CGRequestScreenCaptureAccess on the
    // main thread — this is the officially supported native prompt. Pass
    // true so macOS opens System Settings when the status is already denied.
    mac()?.askForScreenCaptureAccess(true);
    // The underlying API is synchronous but the user's decision is not; give
    // them a beat, then re-check. If still not authorized we return false and
    // the modal falls back to its Settings walkthrough.
    await sleep(600);
    return mac()?.getAuthStatus("screen") === "authorized";
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
  title: "Screen Recording Required",
  body: "Tada needs Screen Recording permission to observe your workflow.",
  steps: [
    "Open System Settings → Privacy & Security → Screen Recording",
    'If Tada isn\'t an option, click the "+" button and select "Tada"',
    'Toggle on "Tada" switch on',
    '(Note: if you\'re in developer mode, you may need to toggle on the terminal switch instead)',
  ],
};

// ── Full Disk Access (shared by notifications + browser cookies) ──────────────

/**
 * node-mac-permissions' FDA check reads `/Library/Application Support/com.apple
 * .TCC/TCC.db` under the hood. That read is itself the TCC registration event
 * (same mechanism as our old manual `fs.openSync` poke), so calling this both
 * returns the current status AND makes Tada appear in the Full Disk Access
 * list in System Settings on first call.
 */
const hasFullDiskAccess = () =>
  mac()?.getAuthStatus("full-disk-access") === "authorized";

const notificationsPermission: PermissionDescriptor = {
  check: hasFullDiskAccess,

  // FDA has no programmatic consent API. `hasFullDiskAccess()` registers the
  // app with TCC (via the internal TCC.db read) so it appears in System
  // Settings, and `askForFullDiskAccess()` opens the pane. Per-folder
  // (Desktop/Documents/Downloads) prompts are handled by their own
  // descriptors below so the user isn't hit with four stacked popups when
  // they click a single "Grant Access" button.
  request: async () => {
    const before = hasFullDiskAccess();
    if (!before) mac()?.askForFullDiskAccess();
    return hasFullDiskAccess();
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
  title: "Full Disk Access Required",
  body: "Tada needs Full Disk Access to read notifications and browser data.",
  steps: [
    "Open System Settings → Privacy & Security → Full Disk Access",
    'If Tada isn\'t an option, click the "+" button and select "Tada"',
    'Toggle on "Tada" switch on',
    '(Note: if you\'re in developer mode, you may need to toggle on the terminal switch instead)',
  ],
};

// ── Protected Folders (Desktop / Documents / Downloads) ──────────────────────
//
// macOS Sonoma+ keeps these three folders as their own TCC classes, separate
// from Full Disk Access. Each one must be asked for individually — `node-mac-
// permissions.askForFoldersAccess` wraps `NSFileManager contentsOfDirectoryAt-
// Path`, which triggers the native prompt the first time TCC has no decision
// and silently returns `authorized`/`denied` thereafter. We expose one
// descriptor per folder so the onboarding UI can render four independent
// "Grant Access" buttons instead of firing all prompts at once.

type ProtectedFolder = "desktop" | "documents" | "downloads";

function makeFolderPermission(
  folder: ProtectedFolder,
  label: string,
): PermissionDescriptor {
  // `asked` guards against re-calling `askForFoldersAccess` from the modal's
  // 1.5s poller before the user has engaged with the prompt at all — that
  // first call is the one that surfaces the native dialog, so we only want
  // it to happen in response to an explicit `request()`. After the user has
  // made a decision once, TCC caches it and subsequent calls are silent, so
  // we can safely re-check on every poll.
  let asked = false;
  let cached: "authorized" | "denied" | null = null;

  const probe = async (): Promise<boolean> => {
    const m = mac();
    if (!m) return false;
    try {
      const result = await m.askForFoldersAccess(folder);
      cached = result === "authorized" ? "authorized" : "denied";
    } catch {
      cached = "denied";
    }
    return cached === "authorized";
  };

  return {
    check: async () => {
      if (hasFullDiskAccess()) return true;
      if (cached === "authorized") return true;
      if (asked) return probe();
      return false;
    },

    request: async () => {
      asked = true;
      if (hasFullDiskAccess()) return true;
      return probe();
    },

    fixUrl:
      "x-apple.systempreferences:com.apple.preference.security?Privacy_FilesAndFolders",
    title: `${label} Folder Access`,
    body: `Tada needs access to your ${label} folder to watch for new files.`,
    steps: [
      `Click "Allow" on the macOS permission prompt for your ${label} folder`,
      `Or: System Settings → Privacy & Security → Files and Folders → toggle ${label} on for Tada`,
    ],
  };
}

const folderDesktopPermission = makeFolderPermission("desktop", "Desktop");
const folderDocumentsPermission = makeFolderPermission("documents", "Documents");
const folderDownloadsPermission = makeFolderPermission("downloads", "Downloads");

// ── Accessibility ────────────────────────────────────────────────────────────

const accessibilityPermission: PermissionDescriptor = {
  check: () => mac()?.getAuthStatus("accessibility") === "authorized",

  request: async () => {
    // askForAccessibilityAccess wraps AXIsProcessTrustedWithOptions(prompt=YES) —
    // (re-)registers the binary in TCC and triggers the native prompt.
    mac()?.askForAccessibilityAccess();
    await sleep(600);
    return mac()?.getAuthStatus("accessibility") === "authorized";
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
  title: "Accessibility Required",
  body: "Tada needs Accessibility permission for Tab autocomplete (Tabracadabra).",
  steps: [
    "Open System Settings → Privacy & Security → Accessibility",
    'Toggle on "Tada" switch on',
    '(Note: if you\'re in developer mode, you may need to toggle on the terminal switch instead)',
  ],
};

// ── Browser Cookies (Chrome — requires Full Disk Access) ─────────────────────

const browserCookiesPermission: PermissionDescriptor = {
  check: hasFullDiskAccess,

  // See note on notificationsPermission.request — `hasFullDiskAccess()` itself
  // registers the app in TCC via its internal TCC.db read, then we open the
  // FDA pane in System Settings for the user to toggle.
  request: async () => {
    const before = hasFullDiskAccess();
    if (!before) mac()?.askForFullDiskAccess();
    return hasFullDiskAccess();
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
  title: "Full Disk Access Required",
  body: "Tada needs Full Disk Access to read Chrome cookies for web browsing.",
  steps: [
    "Open System Settings → Privacy & Security → Full Disk Access",
    'If the Tada isn\'t an option, click the "+" button and select "Tada"',
    'Toggle on "Tada" switch on',
    '(Note: if you\'re in developer mode, you may need to toggle on the terminal switch instead)',
  ],
};

// ── Microphone ──────────────────────────────────────────────────────────────

const microphonePermission: PermissionDescriptor = {
  check: () => systemPreferences.getMediaAccessStatus("microphone") === "granted",

  request: async () => {
    // Both Electron's askForMediaAccess and node-mac-permissions wrap
    // AVCaptureDevice requestAccessForMediaType — Electron is already a
    // first-class implementation here, so no reason to route around it.
    return systemPreferences.askForMediaAccess("microphone");
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone",
  title: "Microphone Access Required",
  body: "Tada needs microphone access to transcribe your speech.",
  steps: [
    "Open System Settings \u2192 Privacy & Security \u2192 Microphone",
    'Toggle on "Tada"',
  ],
};

// ── System Audio (uses Screen Recording via ScreenCaptureKit) ───────────────

const systemAudioPermission: PermissionDescriptor = {
  check: () => mac()?.getAuthStatus("screen") === "authorized",

  request: async () => {
    // ScreenCaptureKit requires Screen Recording permission even for audio-only.
    mac()?.askForScreenCaptureAccess(true);
    await sleep(600);
    return mac()?.getAuthStatus("screen") === "authorized";
  },

  fixUrl: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
  title: "Screen Recording Required for System Audio",
  body: "System audio capture uses ScreenCaptureKit, which requires Screen Recording permission.",
  steps: [
    "Open System Settings \u2192 Privacy & Security \u2192 Screen Recording",
    'Toggle on "Tada"',
    "Restart Tada if prompted",
  ],
};

// ── Registry ──────────────────────────────────────────────────────────────────

export const connectorPermissions: Partial<Record<string, PermissionDescriptor>> = {
  screen: screenPermission,
  notifications: notificationsPermission,
  accessibility: accessibilityPermission,
  browser_cookies: browserCookiesPermission,
  microphone: microphonePermission,
  system_audio: systemAudioPermission,
  folder_desktop: folderDesktopPermission,
  folder_documents: folderDocumentsPermission,
  folder_downloads: folderDownloadsPermission,
};

/** Returns true if the named connector either has no permission requirement or passes its check. */
export async function canUseConnector(name: string): Promise<boolean> {
  return (await connectorPermissions[name]?.check()) ?? true;
}
