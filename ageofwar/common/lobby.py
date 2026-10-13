"""One Activity window's games: every match in it, and the games list for the pages that aren't in one. A page sees one
match at a time, as a player or a watcher, or the list, where it can watch a match or start its own"""

import asyncio
import itertools
import random
import typing as t

from .leaderboard import Result
from .match import Match

# One count for every window, after a prefix drawn each time the cog loads, so a page never mistakes a new match for an
# old one it still shows
IDS = itertools.count(1)
PREFIX = f"{random.getrandbits(24):06x}"

GAME_GONE = "That game has ended."
STILL_PLAYING = "Give up your game first."


class Lobby:
    def __init__(
        self,
        room: t.Any,
        record: t.Callable[[list[Result]], None],
        emptied: t.Callable[["Lobby"], None],
    ):
        """`record(results)` gets each match's wins for the leaderboard. `emptied(lobby)` is called once the window
        has no matches and nobody in it"""
        self.room = room
        self.record = record
        self.emptied = emptied
        self.matches: dict[str, Match] = {}
        # What each page in the list was last sent, so a list that didn't change isn't sent again
        self.sent: dict[int, list] = {}
        # List sends started when a match ended, kept so a task isn't garbage collected halfway
        self.tasks: set[asyncio.Task] = set()
        # The cog is unloading, so matches stopping send nothing
        self.stopping = False

    def new_match(self) -> Match:
        match = Match(f"m{PREFIX}-{next(IDS)}", self.record, self.match_ended)
        match.changed = self.send_lists
        self.matches[match.id] = match
        match.start()
        return match

    def stop(self) -> None:
        self.stopping = True
        for match in list(self.matches.values()):
            match.stop()

    def match_of(self, conn: t.Any) -> Match | None:
        return next((match for match in self.matches.values() if any(c is conn for c in match.audience)), None)

    def seated_match(self, user_id: int) -> Match | None:
        return next((match for match in self.matches.values() if match.seat_of(user_id) is not None), None)

    # ---------- Pages arriving and leaving ----------

    async def join(self, conn: t.Any, follow: int | None = None) -> None:
        """A page arriving: back at the player's own base, with the friend whose Join opened it, straight into a new
        match when the window has none, or else the games list"""
        match = self.seated_match(conn.ctx.author.id)
        if match is None and follow is not None:
            match = next((match for match in self.matches.values() if match.has(follow)), None)
        if match is None and not self.matches:
            match = self.new_match()
        if match is not None:
            await match.join(conn)
        else:
            await self.send_list(conn)

    def leave(self, conn: t.Any) -> None:
        self.sent.pop(id(conn), None)
        match = self.match_of(conn)
        if match is not None:
            match.leave(conn)
        self.check_empty()

    def check_empty(self) -> None:
        if not self.matches and not self.room.connections:
            self.emptied(self)

    # ---------- Messages ----------

    async def message(self, conn: t.Any, data: t.Any) -> None:
        """The list's own messages, or a message for the page's match"""
        if not isinstance(data, dict) or len(data) != 1:
            return
        kind, value = next(iter(data.items()))
        if kind == "games" and value is True:
            await self.to_list(conn)
        elif kind == "new" and value is True:
            await self.start_own(conn)
        elif kind == "watch" and isinstance(value, str):
            await self.watch(conn, value)
        else:
            match = self.match_of(conn)
            if match is not None:
                await match.message(conn, data)

    async def to_list(self, conn: t.Any) -> None:
        match = self.match_of(conn)
        if match is not None and not match.depart(conn):
            await conn.send({"notice": STILL_PLAYING})
            return
        await self.send_list(conn)

    async def start_own(self, conn: t.Any) -> None:
        """A new match, with the player at the left base as its host"""
        if not await self.free(conn):
            return
        match = self.new_match()
        await match.join(conn)
        await match.message(conn, {"sit": 0})

    async def watch(self, conn: t.Any, match_id: str) -> None:
        match = self.matches.get(match_id)
        if match is None:
            await conn.send({"notice": GAME_GONE})
            await self.send_list(conn, force=True)
            return
        if match is self.match_of(conn) or not await self.free(conn):
            return
        await match.join(conn)

    async def free(self, conn: t.Any) -> bool:
        """Takes the page out of its match, unless its player commands a base in a battle there"""
        match = self.match_of(conn)
        if match is not None and not match.depart(conn):
            await conn.send({"notice": STILL_PLAYING})
            return False
        self.sent.pop(id(conn), None)
        return True

    # ---------- The games list ----------

    def games(self) -> list[dict]:
        return [match.summary() for match in self.matches.values()]

    async def send_list(self, conn: t.Any, force: bool = False) -> None:
        games = self.games()
        if force or self.sent.get(id(conn)) != games:
            self.sent[id(conn)] = games
            await conn.send({"games": games})

    async def send_lists(self) -> None:
        """The list to every page in the window that isn't in a match"""
        for conn in self.room.connections:
            if self.match_of(conn) is None:
                await self.send_list(conn)

    def match_ended(self, match: Match) -> None:
        if self.matches.get(match.id) is match:
            del self.matches[match.id]
        self.check_empty()
        # Called as the match's loop stops, so the lists go out on their own task
        if self.room.connections and not self.stopping:
            task = asyncio.create_task(self.send_lists())
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
