import asyncio
import json
import logging
import typing as t

from aiohttp import WSMsgType, web

from .files import build_id, file_response, inject_head, resolve_inside
from .games import Game
from .replies import (
    BAD_REQUEST,
    MAX_BODY,
    NO_CACHE,
    NO_SUCH_ACTION,
    NOT_INSTALLED,
    PAGE_MISSING,
    SESSION_EXPIRED,
    SOMETHING_WRONG,
    STRICT_DUMPS,
    TURNED_OFF,
    error,
    notice_page,
    read_object,
)
from .sessions import ActivityContext
from .sockets import (
    CLOSE_GOING_AWAY,
    CLOSE_HANDLER_FAILED,
    CLOSE_NO_SOCKET,
    CLOSE_SESSION,
    CLOSE_TURNED_OFF,
    PING,
    READY,
    Connection,
)

if t.TYPE_CHECKING:
    from .server import HubServer

log = logging.getLogger("red.vrt.activityhub.game_routes")

READ_METHODS = ("GET", "HEAD")
AUTH_SECONDS = 5
# Cloudflare drops a WebSocket after 100 seconds of silence
HEARTBEAT_SECONDS = 30
CLOSED_TYPES = (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED, WSMsgType.ERROR)
# Sec-Fetch-Dest of a request that loads a whole page, which for a game means its frame went to that address
PAGE_DESTINATIONS = ("iframe", "document")
# Tells hub.fetch that the hub refused the login, not the game's raw route, so logging in again can fix it
EXPIRED_HEADER = {"X-ActivityHub": "session-expired"}


def is_page_load(request: web.Request) -> bool:
    """Whether the browser is loading this address as a page, not fetching a file for one"""
    destination = request.headers.get("Sec-Fetch-Dest")
    if destination is not None:
        return destination in PAGE_DESTINATIONS
    # Browsers that don't send Sec-Fetch-Dest still ask for HTML first when they load a page
    return request.headers.get("Accept", "").startswith("text/html")


def describe(e: Exception) -> str:
    """An exception in one line, like the last line of its traceback"""
    text = str(e)
    return f"{type(e).__name__}: {text}" if text else type(e).__name__


class GameRoutes:
    """Everything under /games/<key>/: the page, its files, actions, raw routes and the live connection"""

    def __init__(self, server: "HubServer"):
        self.server = server
        self.hub = server.hub

    def register(self, app: web.Application) -> None:
        # Games come and go while the server runs, and aiohttp freezes its route list once it starts,
        # so one catch-all route hands each request to whichever game owns the key
        app.router.add_route("*", "/games/{key}/{tail:.*}", self.dispatch)

    async def dispatch(self, request: web.Request) -> web.StreamResponse:
        game = self.hub.registry.games.get(request.match_info["key"])
        tail = request.match_info["tail"]
        if game is None:
            # The menu can still list a game whose cog was just unloaded, so its frame gets a way back.
            # So does a frame that reloads after the cog unloads, on any address under the game
            if request.method in READ_METHODS and (not tail or is_page_load(request)):
                return self.notice(NOT_INSTALLED, 404)
            raise web.HTTPNotFound()
        head, rest = tail.split("/", 1) if "/" in tail else (tail, "")
        if not head:
            return await self.page(request, game)
        if head == "api":
            return await self.action(request, game, rest)
        if head == "ws":
            return await self.socket(request, game)
        if head == "raw":
            return await self.raw(request, game, rest)
        return await self.file(request, game, rest)

    def importmap_tag(self) -> str:
        # "activityhub/..." reaches the hub's own files, which the bundled games share
        hub_root = f"/hub/{self.server.hub_build()}/"
        importmap = json.dumps({"imports": {"activityhub": f"{hub_root}sdk.js", "activityhub/": hub_root}})
        return f'<script type="importmap">{importmap}</script>'

    def notice(self, message: str, status: int) -> web.Response:
        text = inject_head(notice_page(message), self.importmap_tag())
        return web.Response(text=text, content_type="text/html", status=status, headers=NO_CACHE)

    async def something_wrong(self, ctx: ActivityContext | None, reason: str) -> web.Response:
        """The "Something went wrong." reply, plus the reason for the bot owner, who is usually the one testing"""
        if ctx is None or not await self.hub.bot.is_owner(ctx.author):
            return error(SOMETHING_WRONG, 500)
        note = f"Only you see this, as the bot owner: {reason.rstrip('.')}. The bot's log has the full error."
        return error(f"{SOMETHING_WRONG} ({note})", 500)

    async def page(self, request: web.Request, game: Game) -> web.Response:
        if request.method not in READ_METHODS:
            raise web.HTTPMethodNotAllowed(request.method, READ_METHODS)
        if await self.turned_off_here(request, game):
            return self.notice(TURNED_OFF, 403)
        try:
            html = (game.web_dir / "index.html").read_text(encoding="utf-8")
            build = build_id(game.web_dir)
        except (OSError, UnicodeDecodeError) as e:
            # A bundler rebuilding the page can leave index.html missing or half written for a moment.
            # The notice page keeps the frame's button back to the menu, which aiohttp's own 500 page wouldn't
            log.error("Couldn't read index.html of %s", game.key, exc_info=e)
            return self.notice(SOMETHING_WRONG, 500)
        tags = f'<base href="/games/{game.key}/{build}/" />{self.importmap_tag()}'
        return web.Response(text=inject_head(html, tags), content_type="text/html", headers=NO_CACHE)

    async def turned_off_here(self, request: web.Request, game: Game) -> bool:
        # A page load carries no session, so this can only trust the address's guild_id. It is a courtesy:
        # the real locks are on actions, raw routes and the live connection, which use the proven server
        guild_id = request.query.get("guild_id", "")
        return guild_id.isdigit() and await self.server.game_off(int(guild_id), game.key)

    async def file(self, request: web.Request, game: Game, path: str) -> web.StreamResponse:
        if request.method not in READ_METHODS:
            raise web.HTTPMethodNotAllowed(request.method, READ_METHODS)
        target = resolve_inside(game.web_dir, path)
        if target is not None:
            return file_response(target)
        if not is_page_load(request):
            raise web.HTTPNotFound()
        # The game frame itself went to an address that isn't there. A bare 404 would leave the player stuck in it
        log.warning(
            "%s: the game frame went to %r, which isn't a file in web_dir. "
            'Is it an href="#" link, a single-page app router path, or a typo?',
            game.key,
            request.path,
        )
        return self.notice(PAGE_MISSING, 404)

    async def action(self, request: web.Request, game: Game, name: str) -> web.Response:
        if request.method != "POST":
            raise web.HTTPMethodNotAllowed(request.method, ["POST"])
        ctx = self.server.request_context(request)
        if ctx is None:
            return error(SESSION_EXPIRED, 401)
        if await self.server.game_off(ctx.guild_id, game.key):
            return error(TURNED_OFF, 403)
        handler = game.actions.get(name)
        if handler is None:
            return error(NO_SUCH_ACTION.format(name=name), 404)
        data = await read_object(request)
        if data is None:
            return error(BAD_REQUEST, 400)
        try:
            result = await handler(ctx, data)
        except Exception as e:
            log.error("Action %s.%s failed", game.key, name, exc_info=e)
            return await self.something_wrong(ctx, describe(e))
        return await self.reply(ctx, game, name, result)

    async def reply(self, ctx: ActivityContext, game: Game, name: str, result: t.Any) -> web.Response:
        """Turn what an action handler returned into the page's reply"""
        if result is None:
            result = {}
        if not isinstance(result, dict):
            kind = type(result).__name__
            log.error("Action %s.%s returned %s instead of a dict", game.key, name, kind)
            return await self.something_wrong(ctx, f"returned {kind} instead of a dict")
        message = result.get("error")
        if isinstance(message, str) and message.strip():
            return error(message, 400)
        if message is not None:
            # The player would see a Python repr, or an error with no words. {"error": None} is no error
            problem = "an empty error" if isinstance(message, str) else "an error that isn't text"
            log.error("Action %s.%s returned %s: %r", game.key, name, problem, message)
            return await self.something_wrong(ctx, f"returned {problem}: {message!r}")
        try:
            return web.json_response(result, dumps=STRICT_DUMPS)
        except (TypeError, ValueError) as e:
            log.error("Action %s.%s returned something that isn't JSON", game.key, name, exc_info=e)
            return await self.something_wrong(ctx, f"returned something that isn't JSON: {e}")

    async def raw(self, request: web.Request, game: Game, path: str) -> web.StreamResponse:
        handler = game.routes.get((request.method, path.strip("/")))
        if handler is None:
            raise web.HTTPNotFound()
        ctx = self.server.request_context(request)
        if ctx is None and request.headers.get("Authorization", "").startswith("Bearer "):
            # The page sent a login the hub no longer knows: a bot restart, an ActivityHub reload, or 12 hours
            # passed. hub.fetch logs in again and retries, so a handler only sees ctx=None for requests with no
            # login at all
            return web.json_response({"error": SESSION_EXPIRED}, status=401, headers=EXPIRED_HEADER)
        if ctx is not None and await self.server.game_off(ctx.guild_id, game.key):
            return error(TURNED_OFF, 403)
        try:
            response = await handler(request, ctx)
        except web.HTTPException:
            # aiohttp handlers send ready-made responses (redirects, 403s) by raising them
            raise
        except Exception as e:
            log.error("Raw route %s %s of %s failed", request.method, path, game.key, exc_info=e)
            return await self.something_wrong(ctx, describe(e))
        if not isinstance(response, web.StreamResponse):
            log.error("Raw route %s %s of %s returned %r, not a response", request.method, path, game.key, response)
            return await self.something_wrong(ctx, f"returned {type(response).__name__}, not a response")
        return response

    async def socket(self, request: web.Request, game: Game) -> web.StreamResponse:
        if not game.socket:
            return await self.refuse_socket(request, game)
        # Pings are answered in pump, which also needs to see the browser's pongs to notice a player who vanished
        ws = web.WebSocketResponse(max_msg_size=MAX_BODY, autoping=False)
        await ws.prepare(request)
        ctx = await self.socket_context(ws)
        if ctx is None:
            await ws.close(code=CLOSE_SESSION, message=b"Session missing or expired")
            return ws
        if await self.server.game_off(ctx.guild_id, game.key):
            await ws.close(code=CLOSE_TURNED_OFF, message=b"Turned off in this server")
            return ws
        conn = Connection(ws, ctx, game, self.server.rooms)
        # Ready goes out before join, so nothing join sends can reach the page ahead of it
        await conn.send(READY)
        self.server.rooms.add(conn)
        try:
            late_code = await self.late_close_code(conn)
            if late_code is not None:
                await conn.end(late_code)
            elif await self.run_handler(conn, "join"):
                await self.pump(conn)
                # Out of the room before leave runs, so a leave that finds no peers knows it was the last one
                self.server.rooms.discard(conn)
                await self.run_handler(conn, "leave")
        finally:
            self.server.rooms.discard(conn)
            if not ws.closed:
                await conn.end(conn.closing or 1000)
        return ws

    async def refuse_socket(self, request: web.Request, game: Game) -> web.WebSocketResponse:
        """
        Answer a live connection to a game that has no "socket" with close code 4004.
        Refusing the upgrade would reach the page only as 1006, which looks like a network problem
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        # Only after the upgrade, so a plain request to this address isn't reported as a live connection
        log.warning('%s: the page opened a live connection, but activityhub_game() has no "socket"', game.key)
        await ws.close(code=CLOSE_NO_SOCKET, message=b"This game has no live connection")
        return ws

    async def late_close_code(self, conn: Connection) -> int | None:
        """
        Why a connection that just joined its room must close: the game was unloaded or turned off while it waited.
        Closing sweeps only reach connections already in a room, so the room is checked again after joining it
        """
        if self.hub.registry.games.get(conn.game.key) is not conn.game:
            return CLOSE_GOING_AWAY
        if await self.server.game_off(conn.ctx.guild_id, conn.game.key):
            return CLOSE_TURNED_OFF
        return None

    async def socket_context(self, ws: web.WebSocketResponse) -> ActivityContext | None:
        """The player named by the first message, which must carry the session pass in time"""
        try:
            msg = await ws.receive(timeout=AUTH_SECONDS)
        except asyncio.TimeoutError as e:
            log.debug("A live connection sent no session in time: %r", e)
            return None
        if msg.type != WSMsgType.TEXT:
            return None
        try:
            data = json.loads(msg.data)
        except ValueError as e:
            log.debug("A live connection's first message isn't JSON: %s", e)
            return None
        session = data.get("session") if isinstance(data, dict) else None
        return self.server.context_for(session if isinstance(session, str) else None)

    async def run_handler(self, conn: Connection, event: str) -> bool:
        """Call the game's join or leave handler. A raising join closes the connection with 1011"""
        handler = conn.game.socket.get(event)
        if handler is None:
            return True
        try:
            await handler(conn.ctx, conn)
        except Exception as e:
            log.error("Live connection %s handler of %s failed", event, conn.game.key, exc_info=e)
            if event == "join":
                await conn.end(CLOSE_HANDLER_FAILED)
            return False
        return True

    async def pump(self, conn: Connection) -> None:
        """
        Hand each message to the game until the connection closes. A quiet connection gets a heartbeat,
        and one that doesn't answer it is treated as closed
        """
        pinged = False
        while True:
            try:
                msg = await conn.ws.receive(timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError as e:
                if pinged:
                    # Not even the browser's automatic answer to the last ping came back: the player is gone
                    # (a phone that lost its network), so leave runs
                    log.debug("No answer to a heartbeat on %s, closing: %r", conn.game.key, e)
                    conn.closing = CLOSE_GOING_AWAY
                    return
                # The receive timeout is the heartbeat timer: nothing arrived, so send something.
                # Browsers answer protocol pings by themselves; the JSON ping keeps proxies happy
                log.debug("No message in %s seconds, sending a heartbeat: %r", HEARTBEAT_SECONDS, e)
                pinged = True
                await conn.write(conn.ws.ping())
                await conn.send(PING)
                continue
            pinged = False
            if msg.type in CLOSED_TYPES:
                return
            if msg.type == WSMsgType.PING:
                await conn.write(conn.ws.pong(msg.data))
            elif msg.type == WSMsgType.TEXT:
                await self.deliver(conn, msg.data)

    async def deliver(self, conn: Connection, text: str) -> None:
        handler = conn.game.socket.get("message")
        if handler is None:
            return
        try:
            data = json.loads(text)
        except ValueError as e:
            log.debug("Ignored a message that isn't JSON on %s: %s", conn.game.key, e)
            return
        try:
            await handler(conn.ctx, conn, data)
        except Exception as e:
            log.error("Live connection message handler of %s failed", conn.game.key, exc_info=e)
