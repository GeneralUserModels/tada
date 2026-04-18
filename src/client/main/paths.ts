/** Centralized path resolution for dev vs packaged mode. */

import { app } from "electron";
import * as fs from "fs";
import * as path from "path";
import * as os from "os";

export function isDev(): boolean {
  return !app.isPackaged;
}

export function getDataDir(): string {
  if (isDev()) {
    // __dirname is dist/main/ at runtime; project root is two levels up.
    return path.resolve(__dirname, "..", "..");
  }

  const appSupportDir = path.join(os.homedir(), "Library", "Application Support");
  const canonicalDir = path.join(appSupportDir, "tada");
  const legacyDir = path.join(appSupportDir, app.getName());

  // Prefer the canonical, fixed path so launch context does not split app state.
  if (fs.existsSync(canonicalDir)) return canonicalDir;
  if (fs.existsSync(legacyDir)) return legacyDir;
  return canonicalDir;
}

export function getPythonPath(): string {
  return isDev()
    ? path.join(getDataDir(), ".venv", "bin", "python")
    : path.join(getDataDir(), "venv", "bin", "python");
}

export function getUvPath(): string {
  return isDev()
    ? "uv"
    : path.join(getDataDir(), "uv");
}

export function getLogDir(): string {
  return path.join(getDataDir(), "logs");
}

export function getPythonSrcDir(): string {
  return isDev()
    ? path.join(getDataDir(), "src")
    : path.join(process.resourcesPath!, "python-src");
}

export function getRgPath(): string {
  return isDev()
    ? "rg"
    : path.join(getDataDir(), "rg");
}

export function getOutlookTokenPath(): string {
  return path.join(os.homedir(), ".config", "tada", "outlook-token.json");
}

export function getGoogleTokenPath(): string {
  return path.join(os.homedir(), ".config", "tada", "google-token.json");
}
