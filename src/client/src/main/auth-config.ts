/** Auth credentials — loaded from powernap-config.json (single source of truth). */

import * as fs from "fs";
import * as path from "path";
import { getDataDir } from "./paths";

function loadConfig(): Record<string, string> {
  try {
    const configPath = path.join(getDataDir(), "powernap-config.json");
    return JSON.parse(fs.readFileSync(configPath, "utf-8"));
  } catch {
    return {};
  }
}

const _config = loadConfig();

export const GOOGLE_CLIENT_ID = _config.google_client_id ?? "";
export const GOOGLE_CLIENT_SECRET = _config.google_client_secret ?? "";
export const SUPABASE_URL = _config.supabase_url ?? "";
export const SUPABASE_ANON_KEY = _config.supabase_anon_key ?? "";
export const MICROSOFT_CLIENT_ID = _config.microsoft_client_id ?? "";
