"""End-to-end test for the refresh-google-token Supabase edge function.

Flow:
  1. Read ~/.config/tada/google-token.json.
  2. If it has no provider refresh_token (e.g. first run), walk the user through
     a one-time OAuth sign-in with access_type=offline + prompt=consent to get
     one. Saves the updated token.
  3. POST { refresh_token } to the edge function.
  4. Verify the returned access_token works against Gmail.

Prereqs (do these first in Supabase dashboard):
  - Deploy a function named "refresh-google-token" using
    supabase/functions/refresh-google-token/index.ts from this repo.
  - Set Edge Function secrets:
      GOOGLE_CLIENT_ID     = <same id configured on Supabase's Google provider>
      GOOGLE_CLIENT_SECRET = <same secret>

Run:
  uv run python scripts/test_edge_refresh.py
"""

import base64
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

TOKEN_PATH = Path(os.path.expanduser("~/.config/tada/google-token.json"))
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]
EDGE_FN_NAME = "refresh-google-token"


def b64url(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a, **k):
        pass

    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        code = urllib.parse.parse_qs(qs).get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h3>Done. You can close this tab.</h3></body></html>")
        self.server.code = code


def load_token():
    return json.loads(TOKEN_PATH.read_text())


def save_token(t):
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(t, indent=2))


def probe_gmail(access_token):
    req = urllib.request.Request(
        "https://gmail.googleapis.com/gmail/v1/users/me/profile",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"err:{type(e).__name__}"


def one_time_signin_offline(alpha_url, alpha_key):
    """Run the Supabase PKCE flow with access_type=offline + prompt=consent so
    Google issues (and Supabase forwards) a provider_refresh_token."""
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = b64url(hashlib.sha256(code_verifier.encode()).digest())
    port = free_port()
    redirect_uri = f"http://localhost:{port}"

    auth_url = f"{alpha_url}/auth/v1/authorize?" + urllib.parse.urlencode({
        "provider": "google",
        "redirect_to": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "flow_type": "pkce",
        "scopes": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })

    srv = HTTPServer(("127.0.0.1", port), Handler)
    srv.code = None
    Thread(target=srv.serve_forever, daemon=True).start()

    print(f"[signin] opening browser — you'll see Google's consent screen ONCE.")
    subprocess.run(["open", auth_url], check=True)

    t0 = time.time()
    while srv.code is None and time.time() - t0 < 180:
        time.sleep(0.05)
    srv.shutdown()
    if srv.code is None:
        raise RuntimeError("OAuth timed out (3 min)")

    body = json.dumps({"auth_code": srv.code, "code_verifier": code_verifier}).encode()
    req = urllib.request.Request(
        f"{alpha_url}/auth/v1/token?grant_type=pkce",
        data=body,
        headers={"Content-Type": "application/json", "apikey": alpha_key},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        session = json.loads(r.read())

    provider_token = session.get("provider_token", "")
    provider_refresh_token = session.get("provider_refresh_token", "")
    if not provider_token:
        raise RuntimeError("Supabase exchange returned no provider_token")

    return {
        "access_token": provider_token,
        "refresh_token": provider_refresh_token,
        "supabase_refresh_token": session.get("refresh_token", ""),
        "alpha_supabase_url": alpha_url,
        "alpha_supabase_anon_key": alpha_key,
        "expires_at": time.time() * 1000 + session.get("expires_in", 3600) * 1000,
        "scopes": SCOPES,
    }


def call_edge_function(alpha_url, alpha_key, refresh_token):
    url = f"{alpha_url}/functions/v1/{EDGE_FN_NAME}"
    body = json.dumps({"refresh_token": refresh_token}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {alpha_key}",
        "apikey": alpha_key,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main():
    if not TOKEN_PATH.exists():
        print(f"no token at {TOKEN_PATH}. sign in via the app first.")
        return

    token = load_token()
    alpha_url = token.get("alpha_supabase_url", "")
    alpha_key = token.get("alpha_supabase_anon_key", "")
    if not alpha_url or not alpha_key:
        print("token missing alpha_supabase_url / anon_key. sign in via the app first.")
        return

    # Step 1: ensure we have a Google provider_refresh_token.
    if not token.get("refresh_token"):
        print("=== Step 1: no Google refresh_token stored — re-signing in with access_type=offline ===")
        token = one_time_signin_offline(alpha_url, alpha_key)
        save_token(token)
        print(f"[signin] saved. refresh_token len = {len(token['refresh_token'])}")
    else:
        print(f"=== Step 1: already have refresh_token (len={len(token['refresh_token'])}) ===")

    # Step 2: call the edge function.
    print(f"\n=== Step 2: POST to {alpha_url}/functions/v1/{EDGE_FN_NAME} ===")
    t0 = time.time()
    status, body = call_edge_function(alpha_url, alpha_key, token["refresh_token"])
    elapsed = (time.time() - t0) * 1000
    print(f"status: {status}   elapsed: {elapsed:.0f}ms")
    if status != 200:
        print(f"body: {body}")
        print("\nmake sure the edge function is deployed with GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET secrets set.")
        return

    new_access = body.get("access_token", "")
    print(f"new access_token len:   {len(new_access)}")
    print(f"expires_in:             {body.get('expires_in')}")
    print(f"scope:                  {body.get('scope')}")

    # Step 3: verify the fresh token works.
    print(f"\n=== Step 3: Gmail probe with the fresh access_token ===")
    result = probe_gmail(new_access)
    print(f"gmail: {result}")

    # Persist (this is what the real refresh function will do).
    token["access_token"] = new_access
    token["expires_at"] = time.time() * 1000 + body.get("expires_in", 3600) * 1000
    save_token(token)
    print("\ntoken updated on disk. re-run this script to confirm the cycle repeats cleanly.")


if __name__ == "__main__":
    main()
