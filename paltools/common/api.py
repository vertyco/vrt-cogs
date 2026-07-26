import asyncio
import json
import logging
import typing as t

import aiohttp
from pydantic import ValidationError

from .models import PalPlayer, PalResponse, PlayersResponse, ServerInfo, ServerMetrics

log = logging.getLogger("red.vrt.paltools.api")

# One session shared by every server: a per-request ClientSession rebuilds the TCP connector
# and the DNS resolver on every poll tick, for every server, forever.
session: aiohttp.ClientSession | None = None


async def get_session() -> aiohttp.ClientSession:
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession()
    return session


async def close_session() -> None:
    global session
    # Detached before the await, so a request that calls get_session() while the close is in
    # flight installs a fresh session instead of having it dropped on the floor here
    current, session = session, None
    if current is not None and not current.closed:
        await current.close()


class PalApiError(Exception):
    """Base error for PalWorld REST API failures"""


class ServerUnreachable(PalApiError):
    """Connection refused/timed out: server down, wrong host/port, RESTAPIEnabled=False, or firewall"""


class Unauthorized(PalApiError):
    """401: wrong AdminPassword"""


class BadResponse(PalApiError):
    """Non-200 response that is not a 401"""

    def __init__(self, status: int, text: str):
        self.status = status
        self.text = text
        super().__init__(f"HTTP {status}: {text[:200]}")


ModelT = t.TypeVar("ModelT", bound=PalResponse)


class PalClient:
    """Pure aiohttp wrapper for the official PalWorld REST API. No discord imports."""

    def __init__(self, host: str, port: int, admin_password: str, timeout: int = 10):
        self.base_url = f"http://{host}:{port}/v1/api"
        # utf-8, not aiohttp's latin1 default: a password outside latin1 would otherwise raise
        # UnicodeEncodeError inside session.request, sailing past every PalApiError handler
        self.auth = aiohttp.BasicAuth("admin", admin_password, encoding="utf-8")
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def request(self, method: str, endpoint: str, payload: dict | None = None) -> str:
        url = f"{self.base_url}/{endpoint}"
        try:
            client = await get_session()
            async with client.request(method, url, json=payload, auth=self.auth, timeout=self.timeout) as res:
                text = await res.text()
                if res.status == 401:
                    raise Unauthorized("Invalid AdminPassword")
                if res.status != 200:
                    raise BadResponse(res.status, text)
                return text
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            # Everything aiohttp can raise, not just connection errors: a host saved with a scheme
            # or a stray space raises InvalidURL, which callers only handle as a PalApiError
            log.debug("PalWorld request to %s failed: %s", url, e)
            raise ServerUnreachable(str(e)) from e

    async def fetch(self, endpoint: str, model: type[ModelT]) -> ModelT:
        text = await self.request("GET", endpoint)
        try:
            return model.model_validate_json(text)
        except ValidationError as e:
            log.warning("Malformed %s response: %s", endpoint, e)
            raise BadResponse(200, text) from e

    async def info(self) -> ServerInfo:
        return await self.fetch("info", ServerInfo)

    async def players(self) -> list[PalPlayer]:
        return (await self.fetch("players", PlayersResponse)).players

    async def metrics(self) -> ServerMetrics:
        return await self.fetch("metrics", ServerMetrics)

    async def settings(self) -> dict:
        # Live PalWorld servers respond with Content-Type: text/plain even though the body is JSON,
        # so parse the raw text ourselves instead of relying on res.json()'s content-type check.
        text = await self.request("GET", "settings")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # Every caller handles PalApiError, so a raw decode error would sail past them
            log.warning("Malformed settings response: %s", e)
            raise BadResponse(200, text) from e

    async def announce(self, message: str) -> None:
        await self.request("POST", "announce", {"message": message})

    async def kick(self, userid: str, message: str = "You have been kicked") -> None:
        await self.request("POST", "kick", {"userid": userid, "message": message})

    async def ban(self, userid: str, message: str = "You have been banned") -> None:
        await self.request("POST", "ban", {"userid": userid, "message": message})

    async def unban(self, userid: str) -> None:
        await self.request("POST", "unban", {"userid": userid})

    async def save(self) -> None:
        await self.request("POST", "save")

    async def shutdown(self, waittime: int, message: str) -> None:
        await self.request("POST", "shutdown", {"waittime": waittime, "message": message})
