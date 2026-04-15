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

from tenacity import retry, stop_after_attempt, wait_exponential

from fastapi import APIRouter, HTTPException, Request

from server.config import CONFIG_PATH, CONFIG_DEFAULTS_PATH

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
    """Read app-level credentials, layering user config over defaults."""
    merged: dict = {}
    for path in (CONFIG_DEFAULTS_PATH, CONFIG_PATH):
        try:
            merged.update(json.loads(path.read_text()))
        except Exception:
            pass
    return merged


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


def _supabase_rpc(supabase_url: str, anon_key: str, access_token: str, fn_name: str) -> None:
    """Call a Supabase RPC function using the authenticated user's JWT."""
    url = f"{supabase_url}/rest/v1/rpc/{fn_name}"
    req = urllib.request.Request(url, data=b"{}", headers={
        "Content-Type": "application/json",
        "apikey": anon_key,
        "Authorization": f"Bearer {access_token}",
    })
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        logger.warning(f"Supabase RPC {fn_name} failed (non-fatal): {e}")


def _supabase_pkce_exchange(supabase_url: str, anon_key: str, code: str, code_verifier: str) -> dict:
    """Exchange a PKCE auth code for a Supabase session."""
    url = f"{supabase_url}/auth/v1/token?grant_type=pkce"
    body = json.dumps({"auth_code": code, "code_verifier": code_verifier}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "apikey": anon_key,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# ── Google endpoints ───────────────────────────────────────────


@router.post("/google/signin")
async def google_signin():
    """Google sign-in via Supabase OAuth (PKCE flow).

    Opens the browser to Supabase's Google OAuth page, captures the auth code
    via a loopback server, exchanges it for a Supabase session, and extracts
    the user's name and email.
    """
    cfg = _get_app_config()
    supabase_url = cfg.get("supabase_url", "")
    anon_key = cfg.get("supabase_anon_key", "")
    if not supabase_url or not anon_key:
        raise HTTPException(status_code=400, detail="Supabase credentials not configured")

    # PKCE challenge (same pattern as the Outlook flow)
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    port = _free_port()
    redirect_uri = f"http://localhost:{port}"

    auth_url = f"{supabase_url}/auth/v1/authorize?" + urllib.parse.urlencode({
        "provider": "google",
        "redirect_to": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "flow_type": "pkce",
    })

    code = await _oauth_loopback(auth_url, port)
    session = _supabase_pkce_exchange(supabase_url, anon_key, code, code_verifier)

    user = session.get("user", {})
    meta = user.get("user_metadata", {})
    name = meta.get("full_name", meta.get("name", ""))
    email = user.get("email", meta.get("email", ""))

    _supabase_upsert(
        supabase_url,
        anon_key,
        name,
        email,
        meta.get("sub", user.get("id", "")),
    )

    # Record login via RPC (increments counter, etc.)
    access_token = session.get("access_token", "")
    if access_token:
        _supabase_rpc(supabase_url, anon_key, access_token, "record_login")

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
    """Data-access Google OAuth (calendar + gmail scopes) via alpha Supabase project.

    Uses Supabase PKCE flow to get Google provider tokens with Gmail/Calendar
    scopes. The client secret stays in Supabase — never shipped to users.
    """
    state = request.app.state.server
    cfg = _get_app_config()
    alpha_url = cfg.get("alpha_supabase_url", "")
    alpha_key = cfg.get("alpha_supabase_anon_key", "")
    if not alpha_url or not alpha_key:
        raise HTTPException(status_code=400, detail="Alpha Supabase credentials not configured")

    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    port = _free_port()
    redirect_uri = f"http://localhost:{port}"

    auth_url = f"{alpha_url}/auth/v1/authorize?" + urllib.parse.urlencode({
        "provider": "google",
        "redirect_to": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "flow_type": "pkce",
        "scopes": " ".join(GOOGLE_DATA_SCOPES),
    })

    code = await _oauth_loopback(auth_url, port)
    session = _supabase_pkce_exchange(alpha_url, alpha_key, code, code_verifier)

    provider_token = session.get("provider_token", "")
    provider_refresh_token = session.get("provider_refresh_token", "")
    if not provider_token:
        raise HTTPException(status_code=500, detail="No provider token returned from Supabase")

    token = {
        "access_token": provider_token,
        "refresh_token": provider_refresh_token,
        "supabase_refresh_token": session.get("refresh_token", ""),
        "alpha_supabase_url": alpha_url,
        "alpha_supabase_anon_key": alpha_key,
        "expires_at": time.time() * 1000 + 3600 * 1000,
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


# ── Token refresh ─────────────────────────────────────────────

def _refresh_if_expired(token_path: str | None, token_url: str, build_body: Callable, name: str, force: bool = False) -> None:
    """Refresh a single provider's token if expired or expiring within 5 minutes."""
    token = _read_token(token_path) if token_path else None
    if not token or not token.get("refresh_token"):
        return
    if not force and token.get("expires_at", 0) > time.time() * 1000 + 5 * 60 * 1000:
        return
    data = _http_post(token_url, build_body(token))
    token["access_token"] = data["access_token"]
    if "refresh_token" in data:
        token["refresh_token"] = data["refresh_token"]
    token["expires_at"] = time.time() * 1000 + data.get("expires_in", 3600) * 1000
    _write_token(token_path, token)
    logger.info("[auth] %s token refreshed", name)


def _refresh_google_via_supabase(token_path: str | None, force: bool = False) -> None:
    """Refresh Google provider token via the alpha Supabase project."""
    token = _read_token(token_path) if token_path else None
    if not token or not token.get("supabase_refresh_token"):
        return
    if not force and token.get("expires_at", 0) > time.time() * 1000 + 5 * 60 * 1000:
        return
    alpha_url = token.get("alpha_supabase_url", "")
    alpha_key = token.get("alpha_supabase_anon_key", "")
    if not alpha_url or not alpha_key:
        return
    url = f"{alpha_url}/auth/v1/token?grant_type=refresh_token"
    body = json.dumps({"refresh_token": token["supabase_refresh_token"]}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "apikey": alpha_key,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        session = json.loads(resp.read())
    new_provider_token = session.get("provider_token", "")
    if not new_provider_token:
        logger.warning("[auth] Google Supabase refresh returned no provider_token")
        return
    token["access_token"] = new_provider_token
    if session.get("provider_refresh_token"):
        token["refresh_token"] = session["provider_refresh_token"]
    if session.get("refresh_token"):
        token["supabase_refresh_token"] = session["refresh_token"]
    token["expires_at"] = time.time() * 1000 + 3600 * 1000
    _write_token(token_path, token)
    logger.info("[auth] Google token refreshed via Supabase")


def _provider_args(config) -> list[tuple]:
    """Return (token_path, token_url, build_body, name) for each OAuth provider."""
    return [
        (config.outlook_token_path, f"{MICROSOFT_AUTHORITY}/oauth2/v2.0/token",
         lambda t: {"grant_type": "refresh_token", "refresh_token": t["refresh_token"],
                    "client_id": t["client_id"], "scope": " ".join(MICROSOFT_SCOPES)}, "Outlook"),
    ]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _refresh_google_with_retry(token_path: str | None) -> None:
    _refresh_google_via_supabase(token_path, force=True)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _refresh_provider_with_retry(*args) -> None:
    _refresh_if_expired(*args, force=True)


def refresh_expired_tokens(config) -> None:
    """Force-refresh all OAuth tokens at startup with retries."""
    try:
        _refresh_google_with_retry(config.google_token_path)
    except Exception as e:
        logger.warning("[auth] Google startup refresh failed: %s", e)
    for args in _provider_args(config):
        try:
            _refresh_provider_with_retry(*args)
        except Exception as e:
            logger.warning("[auth] %s startup refresh failed: %s", args[3], e)


async def run_token_refresh(config) -> None:
    """Background task: refresh Google & Outlook tokens every 45 minutes."""
    while True:
        try:
            _refresh_google_via_supabase(config.google_token_path)
        except Exception as e:
            logger.warning("[auth] Google token refresh failed: %s", e)
        for args in _provider_args(config):
            try:
                _refresh_if_expired(*args)
            except Exception as e:
                logger.warning("[auth] %s token refresh failed: %s", args[3], e)
        await asyncio.sleep(45 * 60)
