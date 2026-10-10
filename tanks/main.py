import asyncio
import logging
import typing as t
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common.leaderboard import USER_DEFAULTS, Result, add_result, rank
from .common.match import Match

log = logging.getLogger("red.vrt.tanks")


class Tanks(commands.Cog):
    """
    Turn-based artillery for ActivityHub, ported from 2DPlay's Flash game Tanks.

    Up to five players aim, set their power and fire across hills that blow apart, with computer tanks in any seat.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026100902, force_registration=True)
        self.config.register_user(**USER_DEFAULTS)
        # One match per Activity window, keyed by the window's instance id
        self.matches: dict[str, Match] = {}
        # Leaderboard saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()
        # Two windows can finish a match for the same player at once
        self.save_lock = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        await self.config.user_from_id(user_id).clear()

    async def cog_unload(self):
        for match in list(self.matches.values()):
            match.stop()

    async def activityhub_game(self) -> dict:
        return {
            "key": "tanks",
            "name": "Tanks",
            "description": "Aim, power up and blow the hills apart",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.svg",
            "thumbnail": "thumb.png",
            "actions": {"leaderboard": self.leaderboard},
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
        }

    def match_for(self, conn: t.Any) -> Match:
        """The window's match, started when its first player arrives, or again after it stopped"""
        match = self.matches.get(conn.ctx.instance_id)
        if match is None:
            match = Match(conn.room, self.record_match, self.match_ended)
            self.matches[conn.ctx.instance_id] = match
            match.start()
        elif match.room is not conn.room:
            # Reloading ActivityHub gives the window a new room, while the match keeps seats for its dropped players
            match.room = conn.room
        return match

    def match_ended(self, match: Match) -> None:
        if self.matches.get(match.room.instance_id) is match:
            del self.matches[match.room.instance_id]

    async def join(self, ctx, conn) -> None:
        await self.match_for(conn).join(conn)

    async def message(self, ctx, conn, data) -> None:
        await self.match_for(conn).message(conn, data)

    async def leave(self, ctx, conn) -> None:
        # No await before this: the match must see the drop before its loop can decide the window is empty
        match = self.matches.get(ctx.instance_id)
        if match is not None:
            match.leave(conn)

    def record_match(self, results: list[Result]) -> None:
        # Saved off the update loop, after the match, so Config never slows play
        task = asyncio.create_task(self.save_results(results))
        self.saving.add(task)
        task.add_done_callback(self.saving.discard)

    async def save_results(self, results: list[Result]) -> None:
        async with self.save_lock:
            for result in results:
                try:
                    group = self.config.user_from_id(result.user_id)
                    await group.set(add_result(await group.all(), result))
                except Exception as e:
                    log.error("Couldn't save a Tanks result for user %s", result.user_id, exc_info=e)

    async def leaderboard(self, ctx, data: dict) -> dict:
        return rank(await self.config.all_users(), ctx.author.id)
