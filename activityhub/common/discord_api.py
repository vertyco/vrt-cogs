import asyncio
import logging
import typing as t

import aiohttp
import discord
from discord.http import Route
from redbot.core.bot import Red

log = logging.getLogger("red.vrt.activityhub.discord")

# Every call to Discord gives up after this long, so a stuck request can't hang a login
DISCORD_TIMEOUT = aiohttp.ClientTimeout(total=15)
API_BASE = "https://discord.com/api/v10"
TOKEN_URL = f"{API_BASE}/oauth2/token"
ME_URL = f"{API_BASE}/users/@me"
# Interaction response type 12 opens the app's Activity for whoever ran the command or pressed the button
LAUNCH_ACTIVITY = 12
# Command type 4 is the app's Entry Point: what Discord runs when someone starts the Activity from the app launcher,
# in a voice channel, text channel or DM.
# Handler 2 means Discord launches the Activity itself, without asking the bot
ENTRY_POINT = 4
DISCORD_LAUNCHES = 2
DEFAULT_ENTRY_POINT = {
    "name": "launch",
    "description": "Open the games menu",
    "type": ENTRY_POINT,
    "handler": DISCORD_LAUNCHES,
}
# Fields Discord adds to a fetched command that a bulk sync must not send back
READ_ONLY_FIELDS = {"id", "application_id", "version", "guild_id"}
# How long to wait after a 429 that doesn't say how long
DEFAULT_RETRY_AFTER = 5.0


class RateLimited(Exception):
    """
    Discord answered 429. Each 429 counts toward Discord's limit on refused requests, and reaching it bans the
    bot's IP address from the whole API for a while, so the caller must wait retry_after seconds before asking again
    """

    def __init__(self, retry_after: float):
        super().__init__(f"Rate limited, retry after {retry_after:.1f} seconds")
        self.retry_after = retry_after


def retry_after(resp: aiohttp.ClientResponse) -> float:
    try:
        return max(float(resp.headers.get("Retry-After", DEFAULT_RETRY_AFTER)), 0.0)
    except ValueError:
        return DEFAULT_RETRY_AFTER


async def exchange_code(http: aiohttp.ClientSession, client_id: str, secret: str, code: str) -> tuple[str, int] | None:
    """Trade the one-time login code for an access token and the id of the Discord user it belongs to"""
    payload = {"client_id": client_id, "client_secret": secret, "grant_type": "authorization_code", "code": code}
    async with http.post(TOKEN_URL, data=payload) as resp:
        if resp.status == 429:
            raise RateLimited(retry_after(resp))
        if resp.status != 200:
            log.warning("Code exchange failed (%s): %s", resp.status, await resp.text())
            return None
        access_token = (await resp.json())["access_token"]
    async with http.get(ME_URL, headers={"Authorization": f"Bearer {access_token}"}) as resp:
        if resp.status != 200:
            log.warning("User lookup failed (%s): %s", resp.status, await resp.text())
            return None
        return access_token, int((await resp.json())["id"])


async def instance_location(bot: Red, instance_id: str) -> dict | None:
    """Where Discord says an activity instance runs and who is in it, so a page can't claim a different server.
    None when Discord can't find the instance"""
    route = Route(
        "GET",
        "/applications/{application_id}/activity-instances/{instance_id}",
        application_id=bot.application_id,
        instance_id=instance_id,
    )
    try:
        data = await bot.http.request(route)
    except (discord.HTTPException, aiohttp.ClientError) as e:
        log.warning("Activity instance lookup failed for %s: %s", instance_id, e)
        return None
    location = data.get("location") or {}
    guild_id, channel_id = location.get("guild_id"), location.get("channel_id")
    return {
        "guild_id": int(guild_id) if guild_id else None,
        "channel_id": int(channel_id) if channel_id else None,
        "users": [str(user) for user in data.get("users") or []],
    }


async def secret_works(http: aiohttp.ClientSession, client_id: str, secret: str) -> bool:
    """Ask Discord for an app-only token with this secret: it only succeeds when the secret is right"""
    payload = {"client_id": client_id, "client_secret": secret, "grant_type": "client_credentials", "scope": "identify"}
    async with http.post(TOKEN_URL, data=payload) as resp:
        if resp.status != 200:
            log.info("Client secret check failed (%s): %s", resp.status, await resp.text())
        return resp.status == 200


async def activities_enabled(bot: Red) -> bool:
    if bot.application_flags.embedded:
        return True
    # The cached flags are from login, so ask again in case Activities were turned on since
    try:
        info = await bot.application_info()
    except discord.HTTPException as e:
        log.warning("Couldn't fetch application info, trying the launch anyway", exc_info=e)
        return True
    return info.flags.embedded


async def with_entry_point(bot: Red, application_id: int, payload: list[dict]) -> list[dict]:
    """The global command list plus the app's Entry Point. Discord refuses a global sync that leaves the Entry
    Point out, and discord.py doesn't know that command type, so without this every slash sync fails"""
    if any(command.get("type") == ENTRY_POINT for command in payload):
        return payload
    current = await bot.http.get_global_commands(application_id)
    kept = [
        {key: value for key, value in command.items() if key not in READ_ONLY_FIELDS}
        for command in current
        if command.get("type") == ENTRY_POINT
    ]
    if kept:
        return payload + kept
    # Discord makes one when Activities are turned on, but it can go missing. Handler 2 only works with Activities on
    if await activities_enabled(bot):
        return payload + [DEFAULT_ENTRY_POINT]
    return payload


def keep_entry_point(bot: Red) -> t.Callable:
    """Make the bot's global slash sync carry the Entry Point along. Returns the wrapper so unloading can remove it"""
    original = bot.http.bulk_upsert_global_commands

    async def bulk_upsert(application_id: int, payload: list[dict]) -> t.Any:
        return await original(application_id, await with_entry_point(bot, application_id, payload))

    bot.http.bulk_upsert_global_commands = bulk_upsert  # type: ignore[assignment]
    return bulk_upsert


def drop_entry_point_hook(bot: Red, hook: t.Callable) -> None:
    # Only remove our own wrapper, never one another cog put on top of it
    if bot.http.__dict__.get("bulk_upsert_global_commands") is hook:
        del bot.http.bulk_upsert_global_commands


async def launch_activity(bot: Red, interaction: discord.Interaction) -> None:
    """Open the Activity for whoever caused the interaction. Raises discord.HTTPException when Discord refuses"""
    route = Route(
        "POST",
        "/interactions/{interaction_id}/{interaction_token}/callback",
        interaction_id=interaction.id,
        interaction_token=interaction.token,
    )
    await bot.http.request(route, json={"type": LAUNCH_ACTIVITY})


async def ping_public(http: aiohttp.ClientSession, base_url: str, application_id: int) -> str | None:
    """None when <base_url>/hub/api/ping answers with this bot's application id, else what went wrong"""
    url = f"{base_url.rstrip('/')}/hub/api/ping"
    try:
        async with http.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return f"{url} answered with status {resp.status}."
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
        log.info("Public ping to %s failed: %r", url, e)
        return f"Couldn't reach {url} ({type(e).__name__})."
    if not isinstance(data, dict) or data.get("application_id") != str(application_id):
        return f"{url} is answered by something other than this bot's ActivityHub."
    return None
