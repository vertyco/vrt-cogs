import asyncio
import logging
import typing as t

import aiohttp
from redbot.core.i18n import Translator

from .discord_api import (
    DISCORD_TIMEOUT,
    DNS,
    DROPPED,
    NO_MAPPING,
    NOT_HUB,
    REFUSED,
    STATUS,
    TIMEOUT,
    TLS,
    PingFailed,
    activities_enabled,
    ping_hub,
    proxy_url,
    secret_works,
)

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


async def try_ping(http: aiohttp.ClientSession, base_url: str, application_id: int) -> str | PingFailed:
    """The host the hub saw the ping arrive on, or how the ping failed"""
    try:
        return await ping_hub(http, base_url, application_id)
    except PingFailed as e:
        return e


def same_host(seen: str, host: str) -> bool:
    return seen.lower().removesuffix(":443") == host.lower().removesuffix(":443")


def public_problem(failure: PingFailed, host: str) -> str:
    url = f"https://{host}"
    problems = {
        DNS: _(
            "`{host}` doesn't resolve from the bot's machine: it has no DNS record, or the bot's DNS server hasn't "
            "caught up."
        ),
        REFUSED: _("Nothing accepted the connection to `{url}`."),
        TLS: _("`{url}` doesn't have a valid HTTPS certificate."),
        TIMEOUT: _("`{url}` didn't answer within 10 seconds."),
        DROPPED: _("The connection to `{url}` broke before it answered."),
        STATUS: _("`{url}` answered with status {status}."),
    }
    text = problems.get(failure.reason, _("Something other than this bot's ActivityHub answers at `{url}`."))
    return text.format(host=host, url=url, status=failure.status)


def public_result(failure: PingFailed, host: str, port: int, seen: str | None) -> tuple[str, str]:
    """seen is the host Discord's proxy reached the hub through, None when it didn't reach it"""
    problem = public_problem(failure, host)
    if seen is None:
        if failure.reason == DNS:
            fix = _("Add a DNS record for it (a Cloudflare Tunnel public hostname makes one), then check again.")
        else:
            fix = _("Point your tunnel or reverse proxy for `{}` at this bot's web server (port {}).").format(
                host, port
            )
        return FAIL, f"{problem} {fix}"
    # Discord's proxy reaches the hub, so players can play and only the bot's own view is off
    if seen and not same_host(seen, host):
        note = _("Players can play anyway: Discord's URL mapping points at `{}`, not `{}`.").format(seen, host)
    elif failure.reason == DNS:
        note = _(
            "Discord reaches this hub through it, so players can play. The bot's DNS server probably remembered a "
            '"no such name" answer from before the record existed. That clears by itself, usually within 30 minutes, '
            "or flush that DNS server's cache."
        )
    else:
        note = _("Discord reaches this hub through it, so players can play. Only the bot's own machine can't.")
    return WARN, f"{problem} {note}"


async def check_public(hub: t.Any, outcome: str | PingFailed, host: str, seen: str | None) -> tuple[str, str]:
    """Proves the tunnel or proxy reaches this hub: the public address must answer with this bot's id"""
    if not isinstance(outcome, PingFailed):
        return PASS, _("`https://{}` reaches this hub.").format(host)
    return public_result(outcome, host, await hub.config.port(), seen)


def check_mapping(outcome: str | PingFailed, host: str | None, public_works: bool) -> tuple[str, str]:
    """Proves Discord's URL mapping reaches this hub, the same way a player's Activity loads it"""
    if not isinstance(outcome, PingFailed):
        if outcome:
            return PASS, _("Discord's URL mapping reaches this hub through `{}`.").format(outcome)
        return PASS, _("Discord's URL mapping reaches this hub.")
    problems = {
        NO_MAPPING: _(
            "Discord says this bot's Activity isn't available: Activities are off, or the URL mapping is missing."
        ),
        STATUS: _("Through Discord's URL mapping, your public host answered with status {status}."),
        NOT_HUB: _("Through Discord's URL mapping, something other than this bot's ActivityHub answers."),
        TIMEOUT: _("Through Discord's URL mapping, nothing answered within 10 seconds."),
    }
    if outcome.reason not in problems:
        return FAIL, _("Couldn't reach Discord's proxy to test the URL mapping. Try again in a moment.")
    problem = problems[outcome.reason].format(status=outcome.status)
    if host and public_works:
        fix = _(
            "`{0}` works, so set the root mapping `/` to `{0}` in the Developer Portal under Activities > URL Mappings."
        ).format(host)
    else:
        fix = _(
            "In the Developer Portal under Activities > URL Mappings, the root mapping `/` must point to your "
            "public host."
        )
    return FAIL, f"{problem} {fix}"


def check_games(hub: t.Any) -> tuple[str, str]:
    names = sorted(game.name for game in hub.registry.games.values())
    if not names:
        return WARN, _("No activities are installed yet. Install and load a game cog made for ActivityHub.")
    return PASS, _("Activities installed ({}): {}").format(len(names), ", ".join(names))


async def run_checks(hub: t.Any, public_host: str | None, prefix: str) -> list[tuple[str, str]]:
    """Every setup step in order, each as (status, line). The public host is only tested when given"""
    host = normalize_host(public_host) if public_host else None
    app_id = hub.bot.application_id
    async with aiohttp.ClientSession(timeout=DISCORD_TIMEOUT) as http:
        pings = [try_ping(http, proxy_url(app_id), app_id)]
        if host:
            pings.append(try_ping(http, f"https://{host}", app_id))
        secret, activities, mapped, *public = await asyncio.gather(
            check_secret(hub, http, prefix), check_activities(hub), *pings
        )
    results = [await check_server(hub, prefix), secret, activities]
    seen = None if isinstance(mapped, PingFailed) else mapped
    if host:
        results.append(await check_public(hub, public[0], host, seen))
    results.append(check_mapping(mapped, host, bool(public) and not isinstance(public[0], PingFailed)))
    results.append(check_games(hub))
    return results
