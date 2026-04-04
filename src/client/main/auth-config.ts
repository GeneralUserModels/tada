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
export const GOOGLE_CLIENT_SECRET = _config.google_client_secret ?? "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";
export const SUPABASE_URL = _config.supabase_url ?? "https://gicxeybsowfhdanooxdc.supabase.co";
export const SUPABASE_ANON_KEY = _config.supabase_anon_key ?? "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImdpY3hleWJzb3dmaGRhbm9veGRjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMzNjU4ODEsImV4cCI6MjA4ODk0MTg4MX0.MW3S4rCAfQYiTuYvM1MJPL23mr191MPsZe8f6oFMM0I";
