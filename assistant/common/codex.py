"""ChatGPT / Codex subscription auth.

Pure helpers for the OAuth device-code login, token refresh, the Codex CLI's
``auth.json`` file, and the model catalog served by the Codex backend. Nothing here
touches Discord or cog state so it can be unit tested with a stubbed HTTP session.
"""

import asyncio
import base64
import json
import logging
import os
import stat as statmod
import time
import typing as t
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from pydantic import BaseModel

log = logging.getLogger("red.vrt.assistant.codex")

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_AUTH_BASE = "https://auth.openai.com"
CODEX_API_BASE = "https://auth.openai.com/api/accounts"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_DEVICE_URL = "https://auth.openai.com/codex/device"
CODEX_DEVICE_REDIRECT = "https://auth.openai.com/deviceauth/callback"
CODEX_BACKEND_URL = "https://chatgpt.com/backend-api/codex"
CODEX_ORIGINATOR = "codex_cli_rs"
CODEX_CLIENT_VERSION = "0.153.4"
CODEX_DEFAULT_MODEL = "gpt-5.5"
CODEX_REFRESH_WINDOW_SECONDS = 300
CODEX_DEVICE_TIMEOUT_SECONDS = 900
CODEX_CATALOG_TTL_SECONDS = 3600
CODEX_HTTP_TIMEOUT_SECONDS = 30
AUTH_CLAIM = "https://api.openai.com/auth"

# Last parse of the Codex CLI's auth.json, keyed on the file's path and (mtime, size).
AUTH_FILE_CACHE: dict = {"path": None, "stamp": None, "auth": None}


class CodexLoginExpired(Exception):
    """The refresh token is no longer usable; the user must log in again."""


class CodexRefreshFailed(Exception):
    """Transient failure talking to the auth server; the old token is still usable."""


class CodexDeviceLoginUnavailable(Exception):
    """The auth server refused to start a device login (disabled for this workspace)."""


class CodexAuth(BaseModel):
    access_token: str
    refresh_token: str = ""
    id_token: str = ""
    account_id: str
    plan_type: str = ""
    last_refresh: float = 0.0
    source: str = "device"  # device | pasted | file

    def redacted(self) -> str:
        tail = self.account_id[-4:] if self.account_id else "????"
        remaining = expires_at(self) - time.time()
        hours = max(int(remaining // 3600), 0)
        return f"account …{tail}, plan {self.plan_type or 'unknown'}, {self.source}, expires in {hours}h"


class DeviceLogin(BaseModel):
    device_auth_id: str
    user_code: str
    verification_url: str
    interval: int = 5


def parse_jwt_claims(token: str) -> dict:
    """Decode the payload segment of a JWT without verifying the signature."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("token is not a JWT")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError("token payload is not valid JSON") from e


def auth_from_tokens(access_token: str, refresh_token: str, id_token: str, source: str) -> CodexAuth:
    claims = parse_jwt_claims(access_token)
    auth_claim = claims.get(AUTH_CLAIM) or {}
    account_id = auth_claim.get("chatgpt_account_id")
    if not account_id:
        raise ValueError("access token has no chatgpt_account_id claim")
    return CodexAuth(
        access_token=access_token,
        refresh_token=refresh_token or "",
        id_token=id_token or "",
        account_id=account_id,
        plan_type=auth_claim.get("chatgpt_plan_type") or "",
        last_refresh=time.time(),
        source=source,
    )


def expires_at(auth: CodexAuth) -> float:
    try:
        return float(parse_jwt_claims(auth.access_token).get("exp") or 0)
    except ValueError as e:
        log.debug("Could not read exp from Codex access token", exc_info=e)
        return 0.0


def needs_refresh(auth: CodexAuth, now: t.Optional[float] = None) -> bool:
    now = time.time() if now is None else now
    return expires_at(auth) <= now + CODEX_REFRESH_WINDOW_SECONDS


async def refresh(auth: CodexAuth, session: aiohttp.ClientSession) -> CodexAuth:
    """Exchange the refresh token for a new token set.

    Refresh tokens rotate, so the caller must persist the returned auth immediately.
    """
    if not auth.refresh_token:
        raise CodexLoginExpired("this Codex login has no refresh token")
    body = {"client_id": CODEX_CLIENT_ID, "grant_type": "refresh_token", "refresh_token": auth.refresh_token}
    try:
        async with session.post(CODEX_TOKEN_URL, json=body) as res:
            if res.status >= 500:
                raise CodexRefreshFailed(f"auth server returned {res.status}")
            if res.status >= 400:
                text = await res.text()
                log.error(f"Codex token refresh rejected ({res.status}): {text[:300]}")
                raise CodexLoginExpired(f"refresh rejected with {res.status}")
            data = await res.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise CodexRefreshFailed(str(e)) from e
    access = data.get("access_token") or auth.access_token
    fresh = auth_from_tokens(
        access,
        data.get("refresh_token") or auth.refresh_token,
        data.get("id_token") or auth.id_token,
        source=auth.source,
    )
    return fresh


async def start_device_login(session: aiohttp.ClientSession) -> DeviceLogin:
    url = f"{CODEX_API_BASE}/deviceauth/usercode"
    try:
        async with session.post(url, json={"client_id": CODEX_CLIENT_ID}) as res:
            if res.status == 404:
                raise CodexDeviceLoginUnavailable("device code login is disabled for this account")
            if res.status >= 400:
                raise CodexRefreshFailed(f"device code request failed with {res.status}")
            data = await res.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise CodexRefreshFailed(str(e)) from e
    interval = int(str(data.get("interval") or "5").strip() or 5)
    return DeviceLogin(
        device_auth_id=data["device_auth_id"],
        user_code=data.get("user_code") or data.get("usercode"),
        verification_url=CODEX_DEVICE_URL,
        interval=max(interval, 1),
    )


async def exchange_device_code(session: aiohttp.ClientSession, code: str, verifier: str) -> CodexAuth:
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CODEX_DEVICE_REDIRECT,
        "client_id": CODEX_CLIENT_ID,
        "code_verifier": verifier,
    }
    try:
        async with session.post(CODEX_TOKEN_URL, data=form) as res:
            if res.status >= 400:
                text = await res.text()
                raise CodexLoginExpired(f"token exchange failed with {res.status}: {text[:300]}")
            data = await res.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise CodexRefreshFailed(str(e)) from e
    return auth_from_tokens(
        data["access_token"], data.get("refresh_token", ""), data.get("id_token", ""), source="device"
    )


async def poll_device_login(
    session: aiohttp.ClientSession,
    login: DeviceLogin,
    timeout: float = CODEX_DEVICE_TIMEOUT_SECONDS,
    sleep: t.Callable[[float], t.Awaitable[None]] = asyncio.sleep,
    clock: t.Callable[[], float] = time.monotonic,
) -> CodexAuth:
    """Poll until the user approves the code in their browser, then exchange it."""
    url = f"{CODEX_API_BASE}/deviceauth/token"
    body = {"device_auth_id": login.device_auth_id, "user_code": login.user_code}
    start = clock()
    while True:
        try:
            async with session.post(url, json=body) as res:
                if res.status == 200:
                    data = await res.json()
                    return await exchange_device_code(session, data["authorization_code"], data["code_verifier"])
                if res.status not in (403, 404):
                    raise CodexRefreshFailed(f"device auth poll failed with {res.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.debug("Codex device poll network error, retrying", exc_info=e)
        if clock() - start >= timeout:
            raise CodexLoginExpired("device login timed out")
        await sleep(login.interval)


def codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    return Path(override) if override else Path.home() / ".codex"


def load_auth_file(path: Path) -> t.Optional[CodexAuth]:
    """Parse ``auth.json`` at ``path``, returning None when it is missing or unusable."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.debug(f"Could not read {path}", exc_info=e)
        return None
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if not tokens or not tokens.get("access_token") or (data.get("auth_mode") or "chatgpt") != "chatgpt":
        return None
    try:
        return auth_from_tokens(
            tokens["access_token"], tokens.get("refresh_token", ""), tokens.get("id_token", ""), source="file"
        )
    except ValueError as e:
        log.debug(f"{path} holds an unusable token", exc_info=e)
        return None


def stat_auth_file(path: Path) -> t.Optional[tuple[float, int]]:
    """Return the file's (mtime, size), or None when it does not exist."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime, stat.st_size


def read_auth_file() -> t.Optional[CodexAuth]:
    """Load the Codex CLI's ChatGPT login from ``auth.json``, cached on the file's mtime.

    This runs on the event loop for every chat request, so the file is only re-read when it
    actually changes (or appears / disappears).
    """
    path = codex_home() / "auth.json"
    stamp = stat_auth_file(path)
    if AUTH_FILE_CACHE["path"] == str(path) and AUTH_FILE_CACHE["stamp"] == stamp:
        return AUTH_FILE_CACHE["auth"]
    auth = load_auth_file(path)
    AUTH_FILE_CACHE.update(path=str(path), stamp=stamp, auth=auth)
    return auth


def ignore_auth_file() -> None:
    """Stop trusting the host's ``auth.json`` until the file itself changes.

    Used when the login inside it is dead: caching ``None`` against the file's current
    (mtime, size) makes ``read_auth_file`` return None without re-reading, and a fresh
    login written by the Codex CLI changes the stamp and brings it back.
    """
    path = codex_home() / "auth.json"
    AUTH_FILE_CACHE.update(path=str(path), stamp=stat_auth_file(path), auth=None)


def write_auth_file(auth: CodexAuth) -> None:
    """Persist refreshed tokens back into ``auth.json`` so the Codex CLI stays logged in.

    Only the ``tokens`` and ``last_refresh`` keys are rewritten; everything else in the file
    is preserved. Written atomically via a temp file.
    """
    path = codex_home() / "auth.json"
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning(f"Rewriting unreadable {path}", exc_info=e)
            data = {}
    data.setdefault("auth_mode", "chatgpt")
    data.setdefault("OPENAI_API_KEY", None)
    data["tokens"] = {
        "id_token": auth.id_token,
        "access_token": auth.access_token,
        "refresh_token": auth.refresh_token,
        "account_id": auth.account_id,
    }
    data["last_refresh"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    tmp = path.with_suffix(".json.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o600
    try:
        if path.is_file():
            mode = statmod.S_IMODE(path.stat().st_mode)
    except OSError as e:
        log.debug(f"Could not read permissions on {path}", exc_info=e)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2))
    os.replace(tmp, path)
    AUTH_FILE_CACHE.update(path=str(path), stamp=stat_auth_file(path), auth=auth)


def backend_headers(auth: CodexAuth) -> dict[str, str]:
    return {"chatgpt-account-id": auth.account_id, "originator": CODEX_ORIGINATOR}


async def fetch_model_catalog(auth: CodexAuth, session: aiohttp.ClientSession) -> list[str]:
    """Return the chat model slugs the subscription can use (``visibility == "list"``)."""
    url = f"{CODEX_BACKEND_URL}/models?client_version={CODEX_CLIENT_VERSION}"
    headers = {"Authorization": f"Bearer {auth.access_token}", **backend_headers(auth)}
    try:
        async with session.get(url, headers=headers) as res:
            if res.status >= 400:
                raise CodexRefreshFailed(f"model catalog returned {res.status}")
            data = await res.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise CodexRefreshFailed(str(e)) from e
    models: list[str] = []
    for item in data.get("models") or []:
        slug = item.get("slug")
        if slug and item.get("visibility") == "list":
            models.append(slug)
    return models
