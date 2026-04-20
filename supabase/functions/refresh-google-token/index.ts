// Supabase Edge Function — refresh a Google OAuth access_token using the
// user's Google provider_refresh_token.
//
// Client sends: POST { "refresh_token": "1//…" }  + Authorization: Bearer {SUPABASE_ANON_KEY}
// We call Google's /token endpoint server-side (client_id + client_secret stay here)
// and return: { access_token, expires_in, scope, token_type }.
//
// Secrets required (set in Supabase dashboard → Edge Functions → Secrets):
//   GOOGLE_CLIENT_ID       — the same one configured on your Supabase Google provider
//   GOOGLE_CLIENT_SECRET   — ditto
//
// Deploy: paste this into a new function named `refresh-google-token` in the
// Supabase dashboard. Leave "Verify JWT" on (default) — the caller must pass
// a valid anon key / user JWT.

import { serve } from "https://deno.land/std@0.224.0/http/server.ts";

const GOOGLE_CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID");
const GOOGLE_CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET");

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

serve(async (req: Request) => {
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
    return json({ error: "server_misconfigured: missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET" }, 500);
  }

  let body: { refresh_token?: string };
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }
  const refresh_token = body?.refresh_token;
  if (!refresh_token || typeof refresh_token !== "string") {
    return json({ error: "missing_refresh_token" }, 400);
  }

  const googleRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: GOOGLE_CLIENT_ID,
      client_secret: GOOGLE_CLIENT_SECRET,
      refresh_token,
      grant_type: "refresh_token",
    }),
  });

  const text = await googleRes.text();
  if (!googleRes.ok) {
    // Pass Google's error body through so the client can log / surface it.
    return new Response(text, {
      status: googleRes.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  const data = JSON.parse(text);
  return json({
    access_token: data.access_token,
    expires_in: data.expires_in,
    scope: data.scope,
    token_type: data.token_type,
  });
});
