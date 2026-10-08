import asyncio
import logging

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


async def exchange_code(http: aiohttp.ClientSession, client_id: str, secret: str, code: str) -> tuple[str, int] | None:
    """Trade the one-time login code for an access token and the id of the Discord user it belongs to"""
    payload = {"client_id": client_id, "client_secret": secret, "grant_type": "authorization_code", "code": code}
    async with http.post(TOKEN_URL, data=payload) as resp:
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
