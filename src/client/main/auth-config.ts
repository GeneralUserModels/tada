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

export const GOOGLE_CLIENT_ID = _config.google_client_id ?? "892882352791-i0nh6262vjj6lvg26h94j2shfmodbkfu.apps.googleusercontent.com";
export const GOOGLE_CLIENT_SECRET = _config.google_client_secret ?? "YOUR_GOOGLE_CLIENT_SECRET";
export const SUPABASE_URL = _config.supabase_url ?? "https://gicxeybsowfhdanooxdc.supabase.co";
export const SUPABASE_ANON_KEY = _config.supabase_anon_key ?? "sb_publishable_YRwmpMcJTFAlz7tfiMbwYw_pMfFmx4X";
export const MICROSOFT_CLIENT_ID = _config.microsoft_client_id ?? "";
