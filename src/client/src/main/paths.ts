/** Centralized path resolution for dev vs packaged mode. */

import { app } from "electron";
import * as path from "path";
import * as os from "os";

export function isDev(): boolean {
  return !app.isPackaged;
}

export function getDataDir(): string {
  return isDev()
    ? path.resolve(__dirname, "..", "..")
    : app.getPath("userData");
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

export function getOutlookTokenPath(): string {
  return path.join(os.homedir(), ".config", "powernap", "outlook-token.json");
}

export function getGoogleTokenPath(): string {
  return path.join(os.homedir(), ".config", "powernap", "google-token.json");
}
