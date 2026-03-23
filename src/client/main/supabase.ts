/** Lightweight Supabase user upsert via REST API. */

import { net } from "electron";

export interface SupabaseUser {
  name: string;
  email: string;
  googleId: string;
}

export async function upsertUser(
  supabaseUrl: string,
  supabaseKey: string,
  user: SupabaseUser,
): Promise<void> {
  const res = await net.fetch(`${supabaseUrl}/rest/v1/users?on_conflict=google_id`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: supabaseKey,
      Authorization: `Bearer ${supabaseKey}`,
      Prefer: "resolution=merge-duplicates",
    },
    body: JSON.stringify({
      google_id: user.googleId,
      name: user.name,
      email: user.email,
      last_login: new Date().toISOString(),
      login_count: 1,
    }),
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase upsert failed (${res.status}): ${body}`);
  }
}
