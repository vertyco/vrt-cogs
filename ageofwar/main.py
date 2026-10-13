import asyncio
import logging
import typing as t
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common.leaderboard import USER_DEFAULTS, Result, add_result, rank
from .common.lobby import Lobby

log = logging.getLogger("red.vrt.ageofwar")


class AgeOfWar(commands.Cog):
    """
    Age of War for ActivityHub, ported from Louissi's Flash game.

    Defend your base and destroy the enemy's through five ages, from cavemen to super soldiers, against the original's
    computer or a friend.
    """

    __author__ = "Vertyco"
    __version__ = "0.4.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101001, force_registration=True)
        self.config.register_user(**USER_DEFAULTS)
        # Each Activity window's games, keyed by the window's instance id
        self.lobbies: dict[str, Lobby] = {}
        # Leaderboard saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()
        # Two windows can finish a match for the same player at once
        self.save_lock = asyncio.Lock()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        # Behind the save lock, so a win being saved can't write the player back afterwards
        async with self.save_lock:
            await self.config.user_from_id(user_id).clear()

    async def cog_unload(self):
        for lobby in list(self.lobbies.values()):
            lobby.stop()

    async def activityhub_game(self) -> dict:
        return {
            "key": "ageofwar",
            "name": "Age of War",
            "description": "Five ages of war, from cavemen to super soldiers",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "actions": {"leaderboard": self.leaderboard},
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
        }

    def lobby_for(self, conn: t.Any) -> Lobby:
        """The window's games, made when its first player arrives"""
        lobby = self.lobbies.get(conn.ctx.instance_id)
        if lobby is None:
            lobby = Lobby(conn.room, self.record_match, self.lobby_emptied)
            self.lobbies[conn.ctx.instance_id] = lobby
        elif lobby.room is not conn.room:
            # Reloading ActivityHub gives the window a new room, while its matches keep seats for dropped players
            lobby.room = conn.room
        return lobby

    def lobby_emptied(self, lobby: Lobby) -> None:
        if self.lobbies.get(lobby.room.instance_id) is lobby:
            del self.lobbies[lobby.room.instance_id]

    async def join(self, ctx, conn) -> None:
        # Set only on the first connection after a Join in the hub's people list
        await self.lobby_for(conn).join(conn, conn.follow)

    async def message(self, ctx, conn, data) -> None:
        await self.lobby_for(conn).message(conn, data)

    async def leave(self, ctx, conn) -> None:
        # No await before this: the match must see the drop before its loop can decide nobody is left
        lobby = self.lobbies.get(ctx.instance_id)
        if lobby is not None:
            lobby.leave(conn)

    def record_match(self, results: list[Result]) -> None:
        # Saved off the update loop, so Config never slows play
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
                    log.error("Couldn't save an Age of War result for user %s", result.user_id, exc_info=e)

    async def leaderboard(self, ctx, data: dict) -> dict:
        return rank(await self.config.all_users(), ctx.author.id)
