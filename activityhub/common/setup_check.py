import asyncio
import logging
import typing as t

import aiohttp
from redbot.core.i18n import Translator

from .discord_api import DISCORD_TIMEOUT, activities_enabled, ping_public, secret_works

log = logging.getLogger("red.vrt.activityhub.setup_check")
_ = Translator("ActivityHub", __file__)

PASS, WARN, FAIL = "pass", "warn", "fail"
ICONS = {
    PASS: "\N{WHITE HEAVY CHECK MARK}",
    WARN: "\N{WARNING SIGN}\N{VARIATION SELECTOR-16}",
    FAIL: "\N{CROSS MARK}",
}


def normalize_host(value: str) -> str:
    """games.example.com from whatever the owner typed, with or without https:// and slashes"""
    host = value.strip()
    for prefix in ("https://", "http://"):
        host = host.removeprefix(prefix)
    return host.strip("/")


async def check_server(hub: t.Any, prefix: str) -> tuple[str, str]:
    host, port = await hub.config.host(), await hub.config.port()
    if hub.server.running:
        return PASS, _("The web server is running on {}:{}.").format(host, port)
    return FAIL, _(
        "The web server isn't running on {}:{}. Check the bot's logs, or pick another address with "
        "`{}activityhub webserver`."
    ).format(host, port, prefix)


async def check_secret(hub: t.Any, http: aiohttp.ClientSession, prefix: str) -> tuple[str, str]:
    secret = (await hub.bot.get_shared_api_tokens("activityhub")).get("client_secret")
    if not secret:
        return FAIL, _("No client secret is set. Run `{}activityhub secret`.").format(prefix)
    try:
        works = await secret_works(http, str(hub.bot.application_id), secret)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Couldn't reach Discord to check the client secret", exc_info=e)
        return FAIL, _("Couldn't reach Discord to check the client secret. Try again in a moment.")
    if not works:
        return FAIL, _("Discord rejected the saved client secret. Set it again with `{}activityhub secret`.").format(
            prefix
        )
    return PASS, _("The client secret is set and Discord accepts it.")


async def check_activities(hub: t.Any) -> tuple[str, str]:
    if await activities_enabled(hub.bot):
        return PASS, _("Activities are turned on for this bot.")
    return FAIL, _("Activities are off for this bot. Turn them on in the Developer Portal under Activities > Settings.")


async def check_public(hub: t.Any, http: aiohttp.ClientSession, host: str) -> tuple[str, str]:
    """Proves the tunnel or proxy reaches this hub: the public address must answer with this bot's id"""
    problem = await ping_public(http, f"https://{host}", hub.bot.application_id)
    if problem is None:
        return PASS, _("`https://{}` reaches this hub.").format(host)
    port = await hub.config.port()
    return FAIL, _("{} Point your tunnel or reverse proxy for `{}` at this bot's web server (port {}).").format(
        problem, host, port
    )


def check_games(hub: t.Any) -> tuple[str, str]:
    names = sorted(game.name for game in hub.registry.games.values())
    if not names:
        return WARN, _("No activities are installed yet. Install and load a game cog made for ActivityHub.")
    return PASS, _("Activities installed ({}): {}").format(len(names), ", ".join(names))


async def run_checks(hub: t.Any, public_host: str, prefix: str) -> list[tuple[str, str]]:
    """Every setup step in order, each as (status, line)"""
    host = normalize_host(public_host)
    async with aiohttp.ClientSession(timeout=DISCORD_TIMEOUT) as http:
        return [
            await check_server(hub, prefix),
            await check_secret(hub, http, prefix),
            await check_activities(hub),
            await check_public(hub, http, host),
            check_games(hub),
        ]
