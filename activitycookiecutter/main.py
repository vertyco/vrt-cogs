import asyncio
import logging
from pathlib import Path

from redbot.core import commands
from redbot.core.bot import Red

# Type hints for ActivityHub's ctx, conn and room, so the editor can autocomplete them. Copied from ActivityHub's
# devkit folder, as importing ActivityHub itself fails whenever this cog loads first
from .hubtypes import HubConnection, HubContext, HubRoom

log = logging.getLogger("red.vrt.activitycookiecutter")

# How often the bot moves everything and tells every page where it is, in seconds (1 / 20 is 20 times a second).
# 10 to 30 times a second is plenty: the page slides each dot smoothly from one update to the next
TICK = 1 / 20
# The playfield, in made-up units. The page scales it to fit its screen, so a phone and a computer play the same game
WIDTH = 800
HEIGHT = 450
# A dot's size, and how far it moves in a second, in the same units
RADIUS = 20
SPEED = 320
# Where each seat's dot starts: seat 0 on the left, seat 1 on the right
STARTS = ((WIDTH * 0.25, HEIGHT / 2), (WIDTH * 0.75, HEIGHT / 2))
# The only steps a page may ask for on each axis: back, stay, forward
STEPS = (-1, 0, 1)


class Match:
    """One game for everyone in a room: two seats, and anyone else watches"""

    def __init__(self, room: HubRoom):
        # Everyone playing together (by default, everyone in one Activity window). room.broadcast reaches them all
        self.room = room
        # Each seat is None while free, or {"id": user id, "name": shown name, "conn": their live connection}
        self.seats: list[dict | None] = [None, None]
        # Each seat's dot, as [x, y]
        self.spots = [list(start) for start in STARTS]
        # What each seat's player is pressing, as (x step, y step)
        self.moves = [(0, 0), (0, 0)]
        # The update loop (run below) while it is running
        self.task: asyncio.Task | None = None

    def seat_of(self, conn: HubConnection) -> int | None:
        """The seat this connection plays, or None for a watcher"""
        for seat, held in enumerate(self.seats):
            if held is not None and held["conn"] is conn:
                return seat
        return None

    def sit(self, ctx: HubContext, conn: HubConnection) -> int | None:
        """Gives a newcomer a seat and returns it, or returns None when both seats are taken"""
        # A player whose connection dropped and came back gets their own seat back. Their new connection can arrive
        # before the old one's leave has run, so the seat is found by who they are, not by their connection
        for seat, held in enumerate(self.seats):
            if held is not None and held["id"] == ctx.author.id:
                held["conn"] = conn
                return seat
        for seat, held in enumerate(self.seats):
            if held is None:
                self.seats[seat] = {"id": ctx.author.id, "name": ctx.author.display_name, "conn": conn}
                return seat
        return None

    def stand(self, conn: HubConnection) -> bool:
        """Frees the seat this connection played, and says whether it had one"""
        seat = self.seat_of(conn)
        if seat is None:
            return False
        self.seats[seat] = None
        self.spots[seat] = list(STARTS[seat])
        self.moves[seat] = (0, 0)
        return True

    def step(self) -> None:
        """Moves every dot one update forward, by what its player is pressing, and keeps it on the field"""
        for seat, (dx, dy) in enumerate(self.moves):
            spot = self.spots[seat]
            spot[0] = min(WIDTH - RADIUS, max(RADIUS, spot[0] + dx * SPEED * TICK))
            spot[1] = min(HEIGHT - RADIUS, max(RADIUS, spot[1] + dy * SPEED * TICK))

    def seats_message(self) -> dict:
        """Who sits where, sent to everyone each time it changes"""
        return {"seats": [None if held is None else held["name"] for held in self.seats]}

    def spots_message(self) -> dict:
        """Where the dots are, sent to everyone on every update"""
        # Whole numbers in plain lists keep it small, as it goes to every page 20 times a second
        return {"spots": [[round(x), round(y)] for x, y in self.spots]}


class ActivityCookiecutter(commands.Cog):
    """
    A bare-bones two-player ActivityHub game, to copy when starting a new one.

    Two players each move a dot around a shared field, and anyone else in the Activity watches.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        # One match per room, keyed by the room's id
        self.matches: dict[str, Match] = {}

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        # This game saves nothing about anyone, so there is nothing to delete
        return

    async def cog_unload(self):
        for match in self.matches.values():
            if match.task is not None:
                match.task.cancel()

    async def activityhub_game(self) -> dict:
        """ActivityHub calls this by itself when the cog loads, and puts the game in its menu"""
        return {
            # The game's id in the hub, and part of its web address (/games/activitycookiecutter/)
            "key": "activitycookiecutter",
            "name": "Activity Cookiecutter",
            "description": "A bare two-player starter to copy",
            # The folder of web files the hub sends to players. Everything in it is public
            "web_dir": Path(__file__).parent / "web",
            # The live connection: the hub calls join when a page connects, message for each thing a page sends,
            # and leave when a page goes. Listed without brackets
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            # The oldest ActivityHub this game works with: ctx.room_id came in 0.10.0
            "requires": "0.10.0",
        }

    async def join(self, ctx: HubContext, conn: HubConnection):
        match = self.matches.get(ctx.room_id)
        if match is None:
            match = self.matches[ctx.room_id] = Match(conn.room)
        seat = match.sit(ctx, conn)
        # Only the newcomer hears their own seat and the field's size. The room hears who sits where, which reaches
        # the newcomer too, since they are already in the room
        await conn.send({"you": seat, "field": {"width": WIDTH, "height": HEIGHT, "radius": RADIUS, "tick": TICK}})
        await match.room.broadcast(match.seats_message())
        if match.task is None or match.task.done():
            match.task = asyncio.create_task(self.run(match))

    async def message(self, ctx: HubContext, conn: HubConnection, data: object):
        match = self.matches.get(ctx.room_id)
        if match is None:
            return
        seat = match.seat_of(conn)
        if seat is None:
            # Watchers can't move anything
            return
        # Never trust what a page sends: anyone can change their page and send anything. So only the exact message
        # the page is meant to send counts, {"move": [x step, y step]}, and anything else is ignored. type() is int
        # also turns away True and False, which Python counts as 1 and 0
        move = data.get("move") if isinstance(data, dict) else None
        if isinstance(move, list) and len(move) == 2 and all(type(n) is int and n in STEPS for n in move):
            # Stored for the next update, never moved here: the loop moves every dot at the same pace
            match.moves[seat] = (move[0], move[1])

    async def leave(self, ctx: HubContext, conn: HubConnection):
        match = self.matches.get(ctx.room_id)
        if match is None:
            return
        if not conn.peers():
            # The last one out ends the match, and its loop with it
            if match.task is not None:
                match.task.cancel()
            del self.matches[ctx.room_id]
            return
        if match.stand(conn):
            await match.room.broadcast(match.seats_message())

    async def run(self, match: Match):
        """The update loop: moves everything TICK seconds forward, then tells every page where it all is"""
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        try:
            while match.room.connections:
                match.step()
                await match.room.broadcast(match.spots_message())
                # Each update is timed from the start, so small delays never add up into a slower game
                next_tick += TICK
                await asyncio.sleep(max(0.0, next_tick - loop.time()))
        except Exception as e:
            # A background task's error is never shown anywhere unless it is logged
            log.exception("The match loop stopped", exc_info=e)
