import asyncio
import json
import logging
import typing as t

import discord
from aiohttp import web

from . import economy
from .files import file_response, inject_head, resolve_inside
from .game_routes import first_message, pump, session_pass
from .games import Game
from .looks import BUILTIN_LOOK, SettingsError, apply_look_change, effective_look
from .menu import (
    allowed_tabs,
    check_labels,
    games_json,
    merge_disabled,
    merge_order,
    ordered_games,
    player_json,
)
from .replies import (
    BAD_REQUEST,
    INSTANCE_FAILED,
    LOGIN_FAILED,
    MAX_BODY,
    NO_CACHE,
    NOT_ALLOWED,
    NOT_IN_SERVER,
    NOT_SET_UP,
    SESSION_EXPIRED,
    error,
    read_object,
)
from .sessions import ActivityContext, server_admin
from .sockets import CLOSE_SESSION, READY, Connection

if t.TYPE_CHECKING:
    from .server import HubServer

log = logging.getLogger("red.vrt.activityhub.hub_routes")


class HubRoutes:
    """The menu page, the hub's own files, and the /hub/api requests"""

    def __init__(self, server: "HubServer"):
        self.server = server
        self.hub = server.hub
        self.bot = server.bot

    def register(self, app: web.Application) -> None:
        # The API routes go first, since /hub/{build}/{path} would also match them
        app.router.add_get("/hub/api/config", self.config)
        app.router.add_post("/hub/api/token", self.token)
        app.router.add_get("/hub/api/menu", self.menu_state)
        app.router.add_post("/hub/api/settings", self.settings)
        app.router.add_get("/hub/api/ping", self.ping)
        app.router.add_get("/hub/ws", self.menu_link)
        app.router.add_get("/hub/{build}/{path:.+}", self.hub_file)
        app.router.add_get("/", self.menu_page)

    async def menu_page(self, request: web.Request) -> web.Response:
        """The menu, with the login settings written in so the page doesn't wait on a request for them"""
        html = (self.server.web_dir / "index.html").read_text(encoding="utf-8")
        # Escaping "<" keeps the JSON from closing the script tag early
        config = json.dumps(self.client_config()).replace("<", "\\u003c")
        tags = (
            f'<base href="/hub/{self.server.hub_build()}/" />'
            f'<script type="application/json" id="hub-config">{config}</script>'
        )
        return web.Response(text=inject_head(html, tags), content_type="text/html", headers=NO_CACHE)

    async def hub_file(self, request: web.Request) -> web.StreamResponse:
        # Any build code is accepted: it only exists so caches see a new address when files change
        target = resolve_inside(self.server.web_dir, request.match_info["path"])
        if target is None:
            raise web.HTTPNotFound()
        return file_response(target)

    def client_config(self) -> dict:
        scopes = ["identify"] + [scope for scope in self.hub.registry.scopes() if scope != "identify"]
        return {"client_id": str(self.bot.application_id), "scopes": scopes}

    async def config(self, request: web.Request) -> web.Response:
        return web.json_response(self.client_config())

    async def ping(self, request: web.Request) -> web.Response:
        # The host tells the setup check which address Discord's URL mapping points at
        return web.json_response({"application_id": str(self.bot.application_id), "host": request.host})

    async def menu_link(self, request: web.Request) -> web.WebSocketResponse:
        """The menu's live connection for the whole session: where its player is, and who else is in the window"""
        ws = web.WebSocketResponse(max_msg_size=MAX_BODY, autoping=False)
        await ws.prepare(request)
        ctx = self.server.context_for(session_pass(await first_message(ws)))
        if ctx is None:
            await ws.close(code=CLOSE_SESSION, message=b"Session missing or expired")
            return ws
        conn = Connection(ws, ctx, None, None)
        await conn.send(READY)
        presence = self.server.presence
        await presence.connect(conn)
        try:
            await pump(conn, self.menu_message)
        finally:
            presence.disconnect(conn)
            if not ws.closed:
                await conn.end(conn.closing or 1000)
        return ws

    async def menu_message(self, conn: Connection, data: t.Any) -> None:
        try:
            await self.server.presence.update(conn, data)
        except Exception as e:
            log.error("Live connection message handler of %s failed", conn.label, exc_info=e)

    async def token(self, request: web.Request) -> web.Response:
        body = await read_object(request) or {}
        code, instance_id = body.get("code"), body.get("instance_id")
        if not isinstance(code, str) or not isinstance(instance_id, str):
            return error(BAD_REQUEST, 400)
        if not (await self.bot.get_shared_api_tokens("activityhub")).get("client_secret"):
            return error(NOT_SET_UP, 503)
        # The instance lookup only needs the bot's own token, so it runs alongside the login
        login, location = await asyncio.gather(self.server.exchange_code(code), self.server.locate(instance_id))
        if login is None:
            return error(LOGIN_FAILED, 401)
        access_token, user_id = login
        # Failing here instead of treating the player as in a DM keeps turned-off games off.
        # The user must be one of the instance's participants, so a client can't borrow another instance's id
        if location is None:
            return error(INSTANCE_FAILED, 502)
        if str(user_id) not in location["users"]:
            log.info("User %s isn't in activity instance %s", user_id, instance_id)
            return error(INSTANCE_FAILED, 502)
        try:
            ctx = await self.server.make_context(user_id, location, instance_id)
        except discord.HTTPException as e:
            log.error("Couldn't look up Discord user %s", user_id, exc_info=e)
            return error(LOGIN_FAILED, 502)
        if ctx is None:
            return error(NOT_IN_SERVER, 403)
        session = self.hub.sessions.create(ctx)
        # The menu comes back with the login, which saves the page a second request before it can show anything
        return web.json_response(
            {
                "session": session,
                "access_token": access_token,
                "player": player_json(ctx),
                "menu": await self.full_state(ctx),
            }
        )

    async def menu_state(self, request: web.Request) -> web.Response:
        if "Authorization" not in request.headers:
            return web.json_response(await self.preview_state())
        ctx = self.server.request_context(request)
        if ctx is None:
            return error(SESSION_EXPIRED, 401)
        # The menu's badge refresh after a game asks with launch=skip, so a remembered launch waits for a real load
        if request.query.get("launch") == "skip":
            return web.json_response(await self.player_state(ctx))
        return web.json_response(await self.full_state(ctx))

    async def full_state(self, ctx: ActivityContext) -> dict:
        """What the menu shows a logged-in player, including a game to open right away"""
        state = await self.player_state(ctx)
        state["launch"] = await self.take_launch(ctx)
        return state

    async def preview_state(self) -> dict:
        """What the menu shows outside Discord: every game, the owner's look, no settings"""
        global_look = await self.hub.config.look()
        return {
            "player": None,
            "games": games_json(ordered_games(await self.allowed_games(), [])),
            "look": effective_look(global_look),
            "looks": {"builtin": BUILTIN_LOOK, "global": global_look, "guild": {}, "user": {}},
            "tabs": [],
            "switches": [],
            "globalSwitches": [],
            "economyLabels": None,
            "launch": None,
        }

    async def player_state(self, ctx: ActivityContext) -> dict:
        disabled = await self.hub.config.guild(ctx.guild).disabled() if ctx.guild else []
        installed = await self.allowed_games()
        visible = [game for game in installed if game.key not in disabled]
        order = await self.hub.config.user(ctx.author).order()
        looks = await self.player_looks(ctx)
        tabs = await self.player_tabs(ctx)
        switches = [{"key": g.key, "name": g.name, "on": g.key not in disabled} for g in ordered_games(installed, [])]
        shown = ordered_games(visible, order)
        return {
            "player": player_json(ctx),
            "games": games_json(shown, await self.economy_lines(ctx, shown)),
            "look": effective_look(looks["global"], looks["guild"], looks["user"]),
            "looks": looks,
            "tabs": tabs,
            "switches": switches if "server" in tabs else [],
            "globalSwitches": await self.global_switches() if "defaults" in tabs else [],
            "economyLabels": await self.labels_switch(ctx, tabs),
            "launch": None,
        }

    async def global_switches(self) -> list[dict]:
        blocked = await self.hub.config.disabled()
        games = ordered_games(self.hub.registry.games.values(), [])
        return [{"key": g.key, "name": g.name, "on": g.key not in blocked} for g in games]

    async def labels_group(self, guild: discord.Guild | None) -> t.Any:
        """Where the currency labels switch is saved: once for every server when they share one balance"""
        return self.hub.config if await self.hub.payouts.bank.is_global() else self.hub.config.guild(guild)

    async def labels_switch(self, ctx: ActivityContext, tabs: list[str]) -> dict | None:
        """The currency labels switch and the tab holding it, or None when this player has no such tab"""
        tab = "defaults" if await self.hub.payouts.bank.is_global() else "server"
        if tab not in tabs:
            return None
        return {"tab": tab, "on": await (await self.labels_group(ctx.guild)).economy_labels()}

    async def economy_lines(self, ctx: ActivityContext, games: list[Game]) -> dict[str, str | None]:
        """Each shown game's currency line. None outside a server, since a server's bank is what it ties into"""
        if ctx.guild is None or not await (await self.labels_group(ctx.guild)).economy_labels():
            return {}
        return await economy.lines(games, ctx.guild)

    async def allowed_games(self) -> list[Game]:
        """Installed games the bot owner hasn't turned off everywhere"""
        blocked = await self.hub.config.disabled()
        return [game for game in self.hub.registry.games.values() if game.key not in blocked]

    async def player_looks(self, ctx: ActivityContext) -> dict:
        config = self.hub.config
        return {
            "builtin": BUILTIN_LOOK,
            "global": await config.look(),
            "guild": await config.guild(ctx.guild).look() if ctx.guild else {},
            "user": await config.user(ctx.author).look(),
        }

    async def player_tabs(self, ctx: ActivityContext) -> list[str]:
        return allowed_tabs(await server_admin(self.bot, ctx), await self.bot.is_owner(ctx.author))

    async def take_launch(self, ctx: ActivityContext) -> str | None:
        key = self.hub.launches.take(ctx.author.id)
        if key is None or key not in self.hub.registry.games:
            return None
        if await self.server.game_off(ctx.guild_id, key):
            return None
        return key

    async def settings(self, request: web.Request) -> web.Response:
        ctx = self.server.request_context(request)
        if ctx is None:
            return error(SESSION_EXPIRED, 401)
        body = await read_object(request)
        if body is None:
            return error(BAD_REQUEST, 400)
        # Checked on every save: a hidden tab in the page is not the only lock
        tab = body.get("tab")
        if not isinstance(tab, str) or tab not in await self.player_tabs(ctx):
            return error(NOT_ALLOWED, 403)
        try:
            await self.save_tab(ctx, tab, body)
        except SettingsError as e:
            log.debug("Refused a %s settings save: %s", tab, e)
            return error(str(e), 400)
        return web.json_response(await self.player_state(ctx))

    async def save_tab(self, ctx: ActivityContext, tab: str, body: dict) -> None:
        config = self.hub.config
        if tab == "look":
            group = config.user(ctx.author)
            await group.look.set(apply_look_change(await group.look(), body.get("look")))
        elif tab == "order":
            group = config.user(ctx.author)
            await group.order.set(merge_order(await group.order(), body.get("order"), self.hub.registry.games))
        elif tab == "server":
            await self.save_server(ctx.guild, body)
        else:
            await self.save_defaults(body)

    async def save_defaults(self, body: dict) -> None:
        """Save the owner's defaults tab. A missing look, disabled or economyLabels key keeps its saved value"""
        config = self.hub.config
        look, disabled, labels = await config.look(), await config.disabled(), await config.economy_labels()
        if "look" in body:
            look = apply_look_change(look, body["look"])
        if "disabled" in body:
            disabled = merge_disabled(disabled, body["disabled"], self.hub.registry.games)
        # The switch is only here when every server shares one balance
        if await self.hub.payouts.bank.is_global():
            labels = check_labels(body, labels)
        await config.look.set(look)
        await config.disabled.set(disabled)
        await config.economy_labels.set(labels)
        await self.server.rooms.close_games(disabled)

    async def save_server(self, guild: discord.Guild, body: dict) -> None:
        """Save the server tab. A missing look, disabled or economyLabels key keeps its saved value"""
        group = self.hub.config.guild(guild)
        look, disabled, labels = await group.look(), await group.disabled(), await group.economy_labels()
        # Check every part before saving any, so a bad part can't leave a half-saved change
        if "look" in body:
            look = apply_look_change(look, body["look"])
        if "disabled" in body:
            # Games the owner turned off have no switch, so they count as uninstalled and keep this server's choice
            allowed = [game.key for game in await self.allowed_games()]
            disabled = merge_disabled(disabled, body["disabled"], allowed)
        # With a global bank the switch is the owner's, in the defaults tab
        if not await self.hub.payouts.bank.is_global():
            labels = check_labels(body, labels)
        await group.look.set(look)
        await group.disabled.set(disabled)
        await group.economy_labels.set(labels)
        await self.server.rooms.close_off(guild.id, disabled)
