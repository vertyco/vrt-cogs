import asyncio
import logging
import time
import typing as t
import weakref
from collections import deque

from aiohttp import web

from .games import Game
from .replies import dumps
from .sessions import ActivityContext

log = logging.getLogger("red.vrt.activityhub.sockets")

# Hub messages on a live connection. sdk.js handles these itself and never passes them to the game
READY = {"activityhub": "ready"}
PING = {"activityhub": "ping"}
# sdk.js answers PING with this. Some proxies drop WebSocket ping frames, so a page's reply that travels as an
# ordinary message is what proves the player is still there. The hub never hands it to the game
PONG = {"activityhub": "pong"}
# sdk.js times a round trip with {"activityhub": "echo", "t": <its clock>}, and the hub sends it straight back
ECHO = "echo"
RESERVED_FIELD = "activityhub"

CLOSE_GOING_AWAY = 1001
CLOSE_HANDLER_FAILED = 1011
CLOSE_SESSION = 4001
CLOSE_TURNED_OFF = 4003
CLOSE_NO_SOCKET = 4004
# Like HTTP's 429 Too Many Requests: the page sent more than the limits below allow
CLOSE_TOO_MANY = 4029
# The hub's own close codes, kept apart from a game's so the page can always tell what a code means
HUB_CLOSE_CODES = range(4000, 4100)

# A player who can't take a message in this long, or who has this many characters of messages waiting, can't keep
# up and is disconnected. Nobody waits on them meanwhile: each player's messages queue up separately
SEND_SECONDS = 10
OUTBOX_SIZE = 4 * 1024 * 1024

# What a page may send, on average over LIMIT_SECONDS. A game sending an input every frame on a 240 Hz screen stays
# well under it, but a page changed to flood the bot is cut off before it can keep the bot's worker busy
MESSAGES_PER_SECOND = 300
CHARACTERS_PER_SECOND = 1024 * 1024
LIMIT_SECONDS = 5


def forget_failure(sending: asyncio.Future) -> None:
    """Mark a send's error as seen, so asyncio doesn't log it. Its sender handled it, or stopped waiting for it"""
    if not sending.cancelled():
        sending.exception()


def echo_reply(data: t.Any) -> str | None:
    """The answer to sdk.js timing a round trip: its own time, straight back. None for any other message"""
    if not isinstance(data, dict) or data.get(RESERVED_FIELD) != ECHO or len(data) != 2:
        return None
    sent = data.get("t")
    if isinstance(sent, bool) or not isinstance(sent, (int, float)):
        return None
    return dumps({RESERVED_FIELD: ECHO, "t": sent})


class InboxLimit:
    """
    How much more a page may send right now. It refills steadily, so a burst is fine as long as the average over
    LIMIT_SECONDS stays under the limits
    """

    def __init__(self):
        self.messages = MESSAGES_PER_SECOND * LIMIT_SECONDS
        self.characters = CHARACTERS_PER_SECOND * LIMIT_SECONDS
        self.checked = time.monotonic()

    def take(self, size: int) -> bool:
        """Count one message of `size` characters. False once the page has gone over a limit"""
        now = time.monotonic()
        elapsed, self.checked = now - self.checked, now
        self.messages = min(MESSAGES_PER_SECOND * LIMIT_SECONDS, self.messages + elapsed * MESSAGES_PER_SECOND) - 1
        refilled = self.characters + elapsed * CHARACTERS_PER_SECOND
        self.characters = min(CHARACTERS_PER_SECOND * LIMIT_SECONDS, refilled) - size
        return self.messages >= 0 and self.characters >= 0


def to_json(data: t.Any) -> str:
    """The text of a message to the page. Refuses what the page couldn't read, and the hub's own field"""
    if isinstance(data, dict) and RESERVED_FIELD in data and data is not READY and data is not PING:
        # sdk.js would swallow it as one of the hub's own messages, so the game would never see it
        raise ValueError("The 'activityhub' field is reserved for the hub's own messages. Use another field name.")
    return dumps(data)


class Connection:
    """One player's live connection to a game, as the game's socket handlers see it"""

    def __init__(self, ws: web.WebSocketResponse, ctx: ActivityContext, game: Game, rooms: "Rooms"):
        self.ws = ws
        self.ctx = ctx
        self.game = game
        self.rooms = rooms
        # Everyone in this activity instance playing this game. Rooms.add sets it, before join runs
        self.room: Room | None = None
        self.inbox = InboxLimit()
        self.closing: int | None = None
        # Closes a player who stopped taking messages. Kept here so the task isn't garbage collected mid-close
        self.closer: asyncio.Task | None = None
        # Messages and closes waiting to go out to this player, in order, sent one at a time by `writer`. Senders
        # only add to it, so a player whose network stalled never holds up the game or the other players
        self.outbox: deque[str | tuple[int, asyncio.Future]] = deque()
        self.outbox_size = 0
        self.writer: asyncio.Task | None = None

    async def send(self, data: t.Any) -> None:
        """
        Queue a JSON message to this player and return at once. Does nothing once the connection is closing.
        NaN, Infinity and the reserved "activityhub" field raise ValueError, closing or not
        """
        self.queue_text(to_json(data))

    def queue_text(self, text: str) -> None:
        """Queue a message to_json already made. Lets broadcast turn a message into text once for every peer"""
        if self.closing is not None or self.ws.closed:
            return
        if self.outbox_size + len(text) > OUTBOX_SIZE:
            self.let_go(f"more than {OUTBOX_SIZE} characters of messages were waiting for them")
            return
        self.outbox_size += len(text)
        self.outbox.append(text)
        self.wake()

    def wake(self) -> None:
        if self.writer is None or self.writer.done():
            self.writer = asyncio.create_task(self.drain())

    async def drain(self) -> None:
        """
        Send what is queued, one frame at a time. A player's messages arrive in the order they were sent, and
        aiohttp never compresses two of them at once, which can mix up their frames
        """
        while self.outbox:
            item = self.outbox.popleft()
            if isinstance(item, str):
                self.outbox_size -= len(item)
                await self.send_text(item)
                continue
            code, closed = item
            try:
                if self.closing is None:
                    await self.end(code)
            finally:
                if not closed.done():
                    closed.set_result(None)

    async def send_text(self, text: str) -> None:
        if self.closing is not None or self.ws.closed:
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
            self.let_go(f"they couldn't take a message in {SEND_SECONDS} seconds ({e!r})")
        except ConnectionError as e:
            # The player dropped while this was on its way. Their own pump sees that and runs leave
            log.debug("Dropped a message to a closing connection on %s: %s", self.game.key, e)

    def let_go(self, reason: str) -> None:
        """Disconnect a player who can't keep up, and drop the messages waiting for them"""
        if self.closer is not None:
            return
        log.debug("Letting go of a player on %s: %s", self.game.key, reason)
        # Marked closing straight away, so nothing more is queued for them. Their own pump sees the close and
        # runs leave
        self.closing = CLOSE_GOING_AWAY
        self.outbox = deque(item for item in self.outbox if not isinstance(item, str))
        self.outbox_size = 0
        self.closer = asyncio.create_task(self.end(CLOSE_GOING_AWAY))

    async def broadcast(self, data: t.Any, include_self: bool = False) -> None:
        """Queue a message to everyone connected to this game in the same activity instance, and return at once"""
        text = to_json(data)
        for conn in self.peers() + ([self] if include_self else []):
            conn.queue_text(text)

    def peers(self) -> list["Connection"]:
        """The other connections to this game in the same activity instance"""
        return [conn for conn in self.room.connections if conn is not self] if self.room else []

    async def close(self, code: int = 1000) -> None:
        """Close the connection after the messages queued before it. Games use 1000, or their own 4100-4999"""
        if code in HUB_CLOSE_CODES:
            raise ValueError(
                f"Close code {code} is reserved for ActivityHub. Use 1000, or 4100-4999 for your game's own reasons."
            )
        await self.close_after_sends(code)

    async def close_after_sends(self, code: int) -> None:
        """Close with any code once the messages queued before it have gone out, or their player was let go"""
        closed = asyncio.get_running_loop().create_future()
        self.outbox.append((code, closed))
        self.wake()
        await closed

    async def end(self, code: int) -> None:
        """Close with any code right away, dropping messages still queued. The hub's own sweeps use this"""
        self.closing = code
        # Waiting for the send buffer to empty would take forever for a player who stopped reading. The close still
        # goes out after everything sent before it, and the wait for the page's answer to it has its own timeout
        await self.ws.close(code=code, drain=False)


class Room:
    """
    Everyone playing one game in one activity instance, as games see it through conn.room. A game keeps it to reach
    the whole window from a timer, a loop or an action, without picking one player's connection to broadcast from
    """

    def __init__(self, instance_id: str):
        self.instance_id = instance_id
        self.members: list[Connection] = []

    @property
    def connections(self) -> list[Connection]:
        """A copy, so a loop over it can't trip over a player leaving meanwhile"""
        return list(self.members)

    async def broadcast(self, data: t.Any) -> None:
        """Queue a message to everyone in the room, turned into JSON once, and return at once"""
        text = to_json(data)
        for conn in self.members:
            conn.queue_text(text)


class Rooms:
    """Open live connections, grouped by game key and activity instance"""

    def __init__(self):
        self.rooms: dict[tuple[str, str], Room] = {}
        # Rooms everyone left. One the game still holds, like in a loop waiting for its next tick, is handed back
        # when someone returns, so that loop reaches them. One nobody holds is let go
        self.empty: weakref.WeakValueDictionary[tuple[str, str], Room] = weakref.WeakValueDictionary()

    @staticmethod
    def room_key(conn: Connection) -> tuple[str, str]:
        return conn.game.key, conn.ctx.instance_id

    def add(self, conn: Connection) -> None:
        key = self.room_key(conn)
        room = self.rooms.get(key) or self.empty.pop(key, None) or Room(conn.ctx.instance_id)
        self.rooms[key] = room
        room.members.append(conn)
        conn.room = room

    def discard(self, conn: Connection) -> None:
        key = self.room_key(conn)
        room = self.rooms.get(key)
        if room is None:
            return
        if conn in room.members:
            room.members.remove(conn)
        if not room.members:
            del self.rooms[key]
            self.empty[key] = room

    def all(self) -> list[Connection]:
        return [conn for room in self.rooms.values() for conn in room.members]

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
