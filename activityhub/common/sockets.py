import asyncio
import logging
import typing as t

from aiohttp import web

from .games import Game
from .sessions import ActivityContext

log = logging.getLogger("red.vrt.activityhub.sockets")

# Hub messages on a live connection. sdk.js handles these itself and never passes them to the game
READY = {"activityhub": "ready"}
PING = {"activityhub": "ping"}

CLOSE_GOING_AWAY = 1001
CLOSE_HANDLER_FAILED = 1011
CLOSE_SESSION = 4001
CLOSE_TURNED_OFF = 4003


class Connection:
    """One player's live connection to a game, as the game's socket handlers see it"""

    def __init__(self, ws: web.WebSocketResponse, ctx: ActivityContext, game: Game, rooms: "Rooms"):
        self.ws = ws
        self.ctx = ctx
        self.game = game
        self.rooms = rooms
        self.closing: int | None = None

    async def send(self, data: t.Any) -> None:
        """Send a JSON message to this ctx. Does nothing once the connection is closing"""
        if self.ws.closed:
            return
        try:
            await self.ws.send_json(data)
        except ConnectionResetError as e:
            log.debug("Dropped a message to a closing connection on %s: %s", self.game.key, e)

    async def broadcast(self, data: t.Any, include_self: bool = False) -> None:
        """Send to everyone connected to this game in the same activity instance"""
        targets = self.peers() + ([self] if include_self else [])
        await asyncio.gather(*(conn.send(data) for conn in targets))

    def peers(self) -> list["Connection"]:
        """The other connections to this game in the same activity instance"""
        return [conn for conn in self.rooms.room(self) if conn is not self]

    async def close(self, code: int = 1000) -> None:
        self.closing = code
        await self.ws.close(code=code)


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
        results = await asyncio.gather(*(conn.close(code) for conn in targets), return_exceptions=True)
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
