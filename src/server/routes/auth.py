"""OAuth endpoints for Google and Outlook authentication.

All OAuth flows run as async FastAPI endpoints — they start a local loopback
HTTP server, open the system browser, wait for the callback (up to 2 min),
exchange the auth code for tokens, and write the token file that Python
connectors already read via GOOGLE_TOKEN_PATH / OUTLOOK_TOKEN_PATH.

Token refresh runs as asyncio background tasks started in app.py lifespan.
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from server.config import CONFIG_PATH

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Constants ──────────────────────────────────────────────────

GOOGLE_AUTH_SCOPES = ["openid", "email", "profile"]
GOOGLE_DATA_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

MICROSOFT_SCOPES = ["Mail.Read", "Calendars.Read", "User.Read", "offline_access"]
MICROSOFT_AUTHORITY = "https://login.microsoftonline.com/common"
OUTLOOK_REDIRECT_PORT = 48215


# ── Helpers ────────────────────────────────────────────────────

def _get_app_config() -> dict:
    """Read app-level credentials from the config file (client IDs, Supabase)."""
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def _open_url(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", url], check=False)
    elif sys.platform == "win32":
        subprocess.run(["cmd", "/c", "start", "", url], check=False)
    else:
        import webbrowser
        webbrowser.open(url)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _http_post(url: str, params: dict) -> dict:
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


async def _oauth_loopback(auth_url: str, port: int) -> str:
    """Start a loopback HTTP server, open the browser, return the auth code.

    Accepts any request containing a `code` query parameter, regardless of path.
    Closes the server after receiving the code or on timeout (2 min).
    """
    loop = asyncio.get_running_loop()
    code_future: asyncio.Future[str] = loop.create_future()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        code = None
        try:
            data = await asyncio.wait_for(reader.read(8192), timeout=10)
            first_line = data.split(b"\r\n")[0].decode(errors="replace")
            parts = first_line.split(" ")
            if len(parts) >= 2:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(parts[1]).query)
                code = qs.get("code", [None])[0]
                error = qs.get("error", [None])[0]
        except Exception:
            error = "read error"

        if code:
            body = b"<html><body><h3>Signed in! You can close this tab.</h3></body></html>"
        else:
            body = b"<html><body><h3>Done. You can close this tab.</h3></body></html>"

        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + body
        )
        try:
            await writer.drain()
        except Exception:
            pass
        writer.close()

        if not code_future.done():
            if code:
                code_future.set_result(code)
            elif error:
                code_future.set_exception(Exception(f"OAuth error: {error}"))

    server = await asyncio.start_server(handle, "127.0.0.1", port)
    _open_url(auth_url)

    try:
        return await asyncio.wait_for(code_future, timeout=120)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="OAuth timed out (2 min)")
    finally:
        server.close()
        try:
            await asyncio.wait_for(server.wait_closed(), timeout=1.0)
        except Exception:
            pass


def _write_token(path: str, token: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(token, indent=2))


def _read_token(path: str) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None


def _supabase_upsert(supabase_url: str, anon_key: str, name: str, email: str, google_id: str) -> None:
    if not supabase_url or not anon_key:
        return
    url = f"{supabase_url}/rest/v1/users?on_conflict=google_id"
    payload = json.dumps({
        "name": name,
        "email": email,
        "google_id": google_id,
        "last_login": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "Content-Type": "application/json",
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Prefer": "resolution=merge-duplicates",
    })
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        logger.warning(f"Supabase upsert failed (non-fatal): {e}")


# ── Google endpoints ───────────────────────────────────────────

def _google_oauth_exchange(client_id: str, client_secret: str, code: str, redirect_uri: str) -> tuple[dict, dict]:
    """Exchange an auth code for tokens; returns (token_data, user_info)."""
    token_data = _http_post("https://oauth2.googleapis.com/token", {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    id_token = token_data.get("id_token", "")
    payload_b64 = id_token.split(".")[1] if "." in id_token else ""
    padding = "=" * (-len(payload_b64) % 4)
    user_info = json.loads(base64.b64decode(payload_b64 + padding)) if payload_b64 else {}
    return token_data, user_info


@router.post("/google/signin")
async def google_signin():
    """Identity-only Google OAuth (openid/email/profile). No data scopes requested.

    Returns the user's name and email; records them in Supabase. Does not write
    a connector token — use /google/start to grant calendar/gmail access.
    """
    cfg = _get_app_config()
    client_id = cfg.get("google_client_id", "")
    client_secret = cfg.get("google_client_secret", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Google client credentials not configured")

    port = _free_port()
    redirect_uri = f"http://localhost:{port}"

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_AUTH_SCOPES),
        "access_type": "online",
    })

    code = await _oauth_loopback(auth_url, port)
    _, user_info = _google_oauth_exchange(client_id, client_secret, code, redirect_uri)

    name = user_info.get("name", "")
    email = user_info.get("email", "")

    _supabase_upsert(
        cfg.get("supabase_url", ""),
        cfg.get("supabase_anon_key", ""),
        name,
        email,
        user_info.get("sub", ""),
    )

    # Persist to config so the app remembers across restarts
    cfg["google_user_name"] = name
    cfg["google_user_email"] = email
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))

    return {"name": name, "email": email}


@router.get("/google/user")
async def google_user():
    """Return the saved Google user, or null if not signed in."""
    cfg = _get_app_config()
    name = cfg.get("google_user_name", "")
    email = cfg.get("google_user_email", "")
    if name or email:
        return {"name": name, "email": email}
    return None


@router.post("/google/start")
async def google_start(request: Request):
    """Data-access Google OAuth (calendar + gmail scopes). Writes the connector token file."""
    state = request.app.state.server
    cfg = _get_app_config()
    client_id = cfg.get("google_client_id", "")
    client_secret = cfg.get("google_client_secret", "")
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="Google client credentials not configured")

    port = _free_port()
    redirect_uri = f"http://localhost:{port}"

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_DATA_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })

    code = await _oauth_loopback(auth_url, port)
    token_data, _ = _google_oauth_exchange(client_id, client_secret, code, redirect_uri)

    token = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at": time.time() * 1000 + token_data.get("expires_in", 3600) * 1000,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": GOOGLE_DATA_SCOPES,
    }
    _write_token(state.config.google_token_path, token)

    # Re-enable google connectors that were disabled due to errors
    for name, auth in getattr(state, "connector_auth", {}).items():
        if auth == "google":
            if name in state.config.disabled_connectors:
                state.config.disabled_connectors.remove(name)
            state.config.connector_errors.pop(name, None)
            conn = state.connectors.get(name)
            if conn:
                conn.resume()
    state.config.save()

    await state.broadcast("connectors", {})
    return {"ok": True}


@router.delete("/google")
async def google_disconnect(request: Request):
    state = request.app.state.server
    token_path = state.config.google_token_path
    if token_path and Path(token_path).exists():
        Path(token_path).unlink()
    await state.broadcast("connectors", {})
    return {"ok": True}


@router.get("/google/status")
async def google_status(request: Request):
    state = request.app.state.server
    return {"connected": bool(
        state.config.google_token_path and Path(state.config.google_token_path).exists()
    )}


# ── Outlook endpoints ──────────────────────────────────────────

@router.post("/outlook/start")
async def outlook_start(request: Request):
    """Run the Outlook OAuth PKCE flow; blocks until complete or times out."""
    state = request.app.state.server
    cfg = _get_app_config()
    client_id = cfg.get("microsoft_client_id", "")
    if not client_id:
        raise HTTPException(status_code=400, detail="Microsoft client ID not configured")

    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()
    state_param = secrets.token_hex(16)

    redirect_uri = f"http://localhost:{OUTLOOK_REDIRECT_PORT}/auth/callback"
    auth_url = f"{MICROSOFT_AUTHORITY}/oauth2/v2.0/authorize?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(MICROSOFT_SCOPES),
        "state": state_param,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "response_mode": "query",
    })

    code = await _oauth_loopback(auth_url, OUTLOOK_REDIRECT_PORT)

    token_data = _http_post(f"{MICROSOFT_AUTHORITY}/oauth2/v2.0/token", {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
        "scope": " ".join(MICROSOFT_SCOPES),
    })

    token = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_at": time.time() * 1000 + token_data.get("expires_in", 3600) * 1000,
        "client_id": client_id,
        "scopes": MICROSOFT_SCOPES,
    }
    _write_token(state.config.outlook_token_path, token)

    # Re-enable outlook connectors that were disabled due to errors
    for name, auth in getattr(state, "connector_auth", {}).items():
        if auth == "outlook":
            if name in state.config.disabled_connectors:
                state.config.disabled_connectors.remove(name)
            state.config.connector_errors.pop(name, None)
            conn = state.connectors.get(name)
            if conn:
                conn.resume()
    state.config.save()

    await state.broadcast("connectors", {})
    return {"ok": True}


@router.delete("/outlook")
async def outlook_disconnect(request: Request):
    state = request.app.state.server
    token_path = state.config.outlook_token_path
    if token_path and Path(token_path).exists():
        Path(token_path).unlink()
    await state.broadcast("connectors", {})
    return {"ok": True}


@router.get("/outlook/status")
async def outlook_status(request: Request):
    state = request.app.state.server
    return {"connected": bool(
        state.config.outlook_token_path and Path(state.config.outlook_token_path).exists()
    )}


# ── Background token refresh tasks ────────────────────────────

async def _refresh_token_loop(
    config,
    token_path_getter: Callable,
    token_url: str,
    build_body: Callable[[dict], dict],
    name: str,
) -> None:
    while True:
        await asyncio.sleep(45 * 60)
        token_path = token_path_getter(config)
        if not token_path:
            continue
        token = _read_token(token_path)
        if not token or not token.get("refresh_token"):
            continue
        try:
            data = _http_post(token_url, build_body(token))
            token["access_token"] = data["access_token"]
            if "refresh_token" in data:
                token["refresh_token"] = data["refresh_token"]
            token["expires_at"] = time.time() * 1000 + data.get("expires_in", 3600) * 1000
            _write_token(token_path, token)
            logger.info("[auth] %s token refreshed", name)
        except Exception as e:
            logger.warning("[auth] %s token refresh failed: %s", name, e)


async def refresh_google_tokens(config) -> None:
    """Background task: refresh Google access token every 45 minutes."""
    await _refresh_token_loop(
        config,
        token_path_getter=lambda c: c.google_token_path,
        token_url="https://oauth2.googleapis.com/token",
        build_body=lambda t: {
            "grant_type": "refresh_token",
            "refresh_token": t["refresh_token"],
            "client_id": t["client_id"],
            "client_secret": t["client_secret"],
        },
        name="Google",
    )


async def refresh_outlook_tokens(config) -> None:
    """Background task: refresh Outlook access token every 45 minutes."""
    await _refresh_token_loop(
        config,
        token_path_getter=lambda c: c.outlook_token_path,
        token_url=f"{MICROSOFT_AUTHORITY}/oauth2/v2.0/token",
        build_body=lambda t: {
            "grant_type": "refresh_token",
            "refresh_token": t["refresh_token"],
            "client_id": t["client_id"],
            "scope": " ".join(MICROSOFT_SCOPES),
        },
        name="Outlook",
    )
