import asyncio
import logging
import typing as t

from aiohttp import web

from .games import Game
from .replies import STRICT_DUMPS
from .sessions import ActivityContext

log = logging.getLogger("red.vrt.activityhub.sockets")

# Hub messages on a live connection. sdk.js handles these itself and never passes them to the game
READY = {"activityhub": "ready"}
PING = {"activityhub": "ping"}
# sdk.js answers PING with this. Some proxies drop WebSocket ping frames, so a page's reply that travels as an
# ordinary message is what proves the player is still there. The hub never hands it to the game
PONG = {"activityhub": "pong"}
RESERVED_FIELD = "activityhub"

CLOSE_GOING_AWAY = 1001
CLOSE_HANDLER_FAILED = 1011
CLOSE_SESSION = 4001
CLOSE_TURNED_OFF = 4003
CLOSE_NO_SOCKET = 4004
# The hub's own close codes, kept apart from a game's so the page can always tell what a code means
HUB_CLOSE_CODES = range(4000, 4100)

# A player who can't take a message in this long is disconnected, so they can't hold up everyone's broadcasts
SEND_SECONDS = 10


def forget_failure(sending: asyncio.Future) -> None:
    """Mark a send's error as seen, so asyncio doesn't log it. Its sender handled it, or stopped waiting for it"""
    if not sending.cancelled():
        sending.exception()


def to_json(data: t.Any) -> str:
    """The text of a message to the page. Refuses what the page couldn't read, and the hub's own field"""
    if isinstance(data, dict) and RESERVED_FIELD in data and data is not READY and data is not PING:
        # sdk.js would swallow it as one of the hub's own messages, so the game would never see it
        raise ValueError("The 'activityhub' field is reserved for the hub's own messages. Use another field name.")
    return STRICT_DUMPS(data)


class Connection:
    """One player's live connection to a game, as the game's socket handlers see it"""

    def __init__(self, ws: web.WebSocketResponse, ctx: ActivityContext, game: Game, rooms: "Rooms"):
        self.ws = ws
        self.ctx = ctx
        self.game = game
        self.rooms = rooms
        self.closing: int | None = None
        # Closes a player who stopped taking messages. Kept here so the task isn't garbage collected mid-close
        self.closer: asyncio.Task | None = None

    async def send(self, data: t.Any) -> None:
        """
        Send a JSON message to this ctx. Does nothing once the connection is closing.
        NaN, Infinity and the reserved "activityhub" field raise ValueError, closing or not
        """
        await self.send_text(to_json(data))

    async def send_text(self, text: str) -> None:
        """Send a message to_json already made. Lets broadcast turn a message into text once for every peer"""
        if self.ws.closed:
            return
        await self.write(self.ws.send_str(text))

    async def write(self, sending: t.Awaitable[None]) -> None:
        """Wait for one frame to go out, without letting a stalled or dropped player raise into the sender"""
        # A send that takes too long keeps going in the background. Cancelling it would orphan aiohttp's own wait
        # for the network, whose error when the connection finally drops would be logged as never retrieved
        task = asyncio.ensure_future(sending)
        task.add_done_callback(forget_failure)
        try:
            await asyncio.wait_for(asyncio.shield(task), SEND_SECONDS)
        except asyncio.TimeoutError as e:
            log.debug("A player on %s couldn't take a message in %s seconds: %r", self.game.key, SEND_SECONDS, e)
            if self.closer is None:
                # end() marks the connection closed straight away, so later sends to it return at once,
                # and its own pump sees the close and runs leave
                self.closer = asyncio.create_task(self.end(CLOSE_GOING_AWAY))
        except ConnectionError as e:
            # The player dropped while this was on its way. Their own pump sees that and runs leave
            log.debug("Dropped a message to a closing connection on %s: %s", self.game.key, e)

    async def broadcast(self, data: t.Any, include_self: bool = False) -> None:
        """Send to everyone connected to this game in the same activity instance"""
        text = to_json(data)
        targets = self.peers() + ([self] if include_self else [])
        await asyncio.gather(*(conn.send_text(text) for conn in targets))

    def peers(self) -> list["Connection"]:
        """The other connections to this game in the same activity instance"""
        return [conn for conn in self.rooms.room(self) if conn is not self]

    async def close(self, code: int = 1000) -> None:
        """Close the connection. Games use 1000, or their own 4100-4999"""
        if code in HUB_CLOSE_CODES:
            raise ValueError(
                f"Close code {code} is reserved for ActivityHub. Use 1000, or 4100-4999 for your game's own reasons."
            )
        await self.end(code)

    async def end(self, code: int) -> None:
        """Close with any code. The hub's own closes use this"""
        self.closing = code
        # Waiting for the send buffer to empty would take forever for a player who stopped reading. The close still
        # goes out after everything sent before it, and the wait for the page's answer to it has its own timeout
        await self.ws.close(code=code, drain=False)


class Rooms:
    """Open live connections, grouped by game key and activity instance"""

    def __init__(self):
        self.rooms: dict[tuple[str, str], list[Connection]] = {}

    @staticmethod
    def room_key(conn: Connection) -> tuple[str, str]:
        return conn.game.key, conn.ctx.instance_id

    def add(self, conn: Connection) -> None:
        self.rooms.setdefault(self.room_key(conn), []).append(conn)

    def discard(self, conn: Connection) -> None:
        key = self.room_key(conn)
        room = self.rooms.get(key, [])
        if conn in room:
            room.remove(conn)
        if not room:
            self.rooms.pop(key, None)

    def room(self, conn: Connection) -> list[Connection]:
        return list(self.rooms.get(self.room_key(conn), []))

    def all(self) -> list[Connection]:
        return [conn for room in self.rooms.values() for conn in room]

    async def close_where(self, should_close: t.Callable[[Connection], bool], code: int) -> None:
        targets = [conn for conn in self.all() if should_close(conn)]
        results = await asyncio.gather(*(conn.end(code) for conn in targets), return_exceptions=True)
        for conn, result in zip(targets, results):
            if isinstance(result, BaseException):
                log.warning("Couldn't close a live connection on %s", conn.game.key, exc_info=result)

    async def close_stale(self, games: dict[str, Game]) -> None:
        """Close connections whose game was unloaded, or replaced by a reloaded copy"""
        await self.close_where(lambda conn: games.get(conn.game.key) is not conn.game, CLOSE_GOING_AWAY)

    async def close_off(self, guild_id: int, keys: t.Collection[str]) -> None:
        """Close connections to games an admin just turned off in that server"""
        await self.close_where(lambda conn: conn.ctx.guild_id == guild_id and conn.game.key in keys, CLOSE_TURNED_OFF)

    async def close_games(self, keys: t.Collection[str]) -> None:
        """Close connections to games the bot owner just turned off everywhere"""
        await self.close_where(lambda conn: conn.game.key in keys, CLOSE_TURNED_OFF)

    async def close_all(self) -> None:
        await self.close_where(lambda conn: True, CLOSE_GOING_AWAY)
