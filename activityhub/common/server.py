import asyncio
import logging
import typing as t
from pathlib import Path

import aiohttp
import discord
from aiohttp import web

from . import discord_api
from .files import build_id
from .game_routes import GameRoutes
from .hub_routes import HubRoutes
from .replies import MAX_BODY
from .sessions import ActivityContext
from .sockets import Rooms

log = logging.getLogger("red.vrt.activityhub.server")

HUB_WEB_DIR = Path(__file__).parent.parent / "web"


class HubServer:
    """The hub's web server: the menu, the hub's files and requests, and every game"""

    def __init__(self, hub: t.Any, web_dir: Path = HUB_WEB_DIR):
        self.hub = hub
        self.bot = hub.bot
        self.web_dir = web_dir
        self.rooms = Rooms()
        self.runner: web.AppRunner | None = None
        self.http: aiohttp.ClientSession | None = None

    @property
    def running(self) -> bool:
        return self.runner is not None

    def make_app(self) -> web.Application:
        app = web.Application(client_max_size=MAX_BODY)
        HubRoutes(self).register(app)
        GameRoutes(self).register(app)
        # aiohttp waits up to 60 seconds for open WebSocket handlers on shutdown, so close them first
        app.on_shutdown.append(self.on_shutdown)
        return app

    async def on_shutdown(self, app: web.Application) -> None:
        await self.rooms.close_all()

    async def start(self, host: str, port: int) -> None:
        self.http = aiohttp.ClientSession(timeout=discord_api.DISCORD_TIMEOUT)
        runner = web.AppRunner(self.make_app())
        try:
            await runner.setup()
            await web.TCPSite(runner, host, port).start()
        except Exception as e:
            # Not only OSError: a port past 65535 or an overlong host name fail with other types
            log.debug("ActivityHub web server failed to start on %s:%s: %r", host, port, e)
            await runner.cleanup()
            await self.http.close()
            self.http = None
            raise
        self.runner = runner
        log.info("ActivityHub web server listening on %s:%s", host, port)

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        if self.http:
            await self.http.close()
            self.http = None

    def hub_build(self) -> str:
        return build_id(self.web_dir)

    def context_for(self, token: str | None) -> ActivityContext | None:
        session = self.hub.sessions.get(token)
        return session.ctx if session else None

    def request_context(self, request: web.Request) -> ActivityContext | None:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        return self.context_for(header.removeprefix("Bearer "))

    async def game_off(self, guild_id: int | None, key: str) -> bool:
        """Whether the bot owner turned this game off everywhere, or an admin turned it off in that server"""
        if key in await self.hub.config.disabled():
            return True
        if guild_id is None:
            return False
        return key in await self.hub.config.guild_from_id(guild_id).disabled()

    async def exchange_code(self, code: str) -> tuple[str, int] | None:
        tokens = await self.bot.get_shared_api_tokens("activityhub")
        client_id, secret = str(self.bot.application_id), tokens.get("client_secret", "")
        try:
            return await discord_api.exchange_code(self.http, client_id, secret, code)
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError, ValueError) as e:
            log.error("Discord login exchange failed", exc_info=e)
            return None

    async def locate(self, instance_id: str) -> dict | None:
        return await discord_api.instance_location(self.bot, instance_id)

    async def make_context(self, user_id: int, location: dict, instance_id: str) -> ActivityContext | None:
        """The proven ctx, or None when they aren't a member of the server Discord named"""
        user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
        # A server the bot isn't in (possible with user-installed apps) counts as no server
        guild = self.bot.get_guild(location["guild_id"]) if location["guild_id"] else None
        member = None
        if guild is not None:
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound as e:
                    log.info("User %s isn't in %s: %s", user_id, guild.id, e)
                    return None
        return ActivityContext(
            author=member or user, guild=guild, channel_id=location["channel_id"], instance_id=instance_id
        )
