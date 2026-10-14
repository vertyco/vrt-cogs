import asyncio
import logging
import time
import typing as t
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .common import scores
from .common.game import Game, read_command
from .common.stages import BY_CODE, STAGES

log = logging.getLogger("red.vrt.bloxorz")

KEY = "bloxorz"
# A player's page can be gone this long before their attempt is dropped, leaving only the saved run
HOLD_SECONDS = 60
ELSEWHERE = "Bloxorz was opened somewhere else."
STOPPED = "Something went wrong, so the game was stopped."
TAKEN_OVER = 4100


class Bloxorz(commands.Cog):
    """
    Roll a block across floating stone stages, for ActivityHub.

    A single-player remake of the 2007 Flash puzzle Bloxorz. Each player's run and best scores follow them to
    every server.
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, identifier=2026101301, force_registration=True)
        self.config.register_user(run={}, best={}, name="", reached=0)
        # One game per Discord user: the run follows the player to every server and DM
        self.games: dict[int, Game] = {}
        # Each player's newest page. A newer one takes the game over
        self.conns: dict[int, t.Any] = {}
        # The saved run last sent to each connected page, so `saved` goes out only when it changes
        self.known: dict[int, dict | None] = {}
        # Timers that drop an attempt whose page left, by player
        self.holds: dict[int, asyncio.TimerHandle] = {}
        self.locks: dict[int, asyncio.Lock] = {}
        # Saves in progress, kept so a task isn't garbage collected halfway
        self.saving: set[asyncio.Task] = set()

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        await asyncio.gather(*self.saving, return_exceptions=True)
        async with self.lock_for(user_id):
            await self.config.user_from_id(user_id).clear()
        self.drop(user_id)
        self.known.pop(user_id, None)

    async def cog_unload(self):
        for handle in self.holds.values():
            handle.cancel()
        self.holds.clear()
        await asyncio.gather(*self.saving, return_exceptions=True)

    async def activityhub_game(self) -> dict:
        return {
            "key": KEY,
            "name": "Bloxorz",
            "description": "Roll a block across floating stone stages and stand it in the hole",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "actions": {"leaderboard": self.leaderboard},
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
            "requires": "0.11.0",
        }

    def lock_for(self, user_id: int) -> asyncio.Lock:
        return self.locks.setdefault(user_id, asyncio.Lock())

    def drop(self, user_id: int) -> None:
        """Forget a player's game and the timer that was holding it"""
        self.games.pop(user_id, None)
        handle = self.holds.pop(user_id, None)
        if handle is not None:
            handle.cancel()

    def expire(self, user_id: int, game: Game) -> None:
        """The hold ran out: the attempt goes, the saved run stays in Config"""
        self.holds.pop(user_id, None)
        if self.games.get(user_id) is game and user_id not in self.conns:
            del self.games[user_id]

    @staticmethod
    def board_name(ctx: t.Any) -> str:
        """The Discord-wide name, since the leaderboard covers every server"""
        author = ctx.author
        return author.global_name or author.name

    async def saved_run(self, user_id: int) -> dict | None:
        """The player's saved run: the live game's if there is one, else what Config holds"""
        game = self.games.get(user_id)
        if game is not None:
            return game.saved
        # Behind the player's lock, so a save still in flight is read after it lands
        async with self.lock_for(user_id):
            # Stored as an empty dict when there is no run: Config cannot merge a stored dict into a None default
            return await self.config.user_from_id(user_id).run() or None

    # ---------- Connections ----------

    async def join(self, ctx: t.Any, conn: t.Any) -> None:
        user_id = ctx.author.id
        old = self.conns.get(user_id)
        self.conns[user_id] = conn
        handle = self.holds.pop(user_id, None)
        if handle is not None:
            handle.cancel()
        if old is not None and old is not conn:
            await old.send({"elsewhere": ELSEWHERE})
            await old.close(TAKEN_OVER)
        saved = await self.saved_run(user_id)
        self.known[user_id] = saved
        game = self.games.get(user_id)
        live = game.resume() if game is not None else None
        await conn.send({"hello": {"saved": saved, "game": live}})

    async def leave(self, ctx: t.Any, conn: t.Any) -> None:
        user_id = ctx.author.id
        # A page that was taken over leaves after its replacement joined
        if self.conns.get(user_id) is not conn:
            return
        del self.conns[user_id]
        self.known.pop(user_id, None)
        game = self.games.get(user_id)
        if game is None:
            return
        if game.attempt is None:
            self.drop(user_id)
            return
        loop = asyncio.get_running_loop()
        self.holds[user_id] = loop.call_later(HOLD_SECONDS, self.expire, user_id, game)

    async def message(self, ctx: t.Any, conn: t.Any, data: t.Any) -> None:
        user_id = ctx.author.id
        command = read_command(data)
        if command is None or self.conns.get(user_id) is not conn:
            return
        try:
            await self.handle(ctx, conn, *command)
        except Exception as e:
            log.error("A Bloxorz game failed for user %s", user_id, exc_info=e)
            self.drop(user_id)
            await conn.send({"stopped": STOPPED})

    async def handle(self, ctx: t.Any, conn: t.Any, name: str, value: t.Any) -> None:
        user_id = ctx.author.id
        game = self.games.get(user_id)
        if name in ("new", "passcode", "continue"):
            game = game or Game(time.monotonic)
            messages = await self.begin(user_id, game, name, value)
            if messages is None:
                return
            self.games[user_id] = game
        elif game is None:
            return
        else:
            messages = game.handle(name, value)
        for message in messages:
            await conn.send(message)
        await self.sync(ctx, conn, game)

    async def begin(self, user_id: int, game: Game, name: str, value: t.Any) -> list[dict] | None:
        """The messages that start a run, or None when there is nothing to answer"""
        if name == "new":
            return game.start(1, 0, 0, 0, True)
        if name == "passcode":
            stage = BY_CODE.get(value)
            # A wrong code gets no answer, as in the original
            return None if stage is None else game.start(stage, 0, 0, 0, True)
        saved = await self.saved_run(user_id)
        if saved is None:
            return [{"saved": None}]
        return game.start(saved["stage"], saved["moves"], saved["falls"], saved["seconds"], False)

    async def sync(self, ctx: t.Any, conn: t.Any, game: Game) -> None:
        """Tell the page the saved run when it changed, and save it with any stages the message cleared"""
        user_id = ctx.author.id
        cleared, game.cleared = game.cleared, []
        saved = game.saved
        changed = saved != self.known.get(user_id)
        if changed:
            self.known[user_id] = saved
            await conn.send({"saved": saved})
        if changed or cleared:
            task = asyncio.create_task(self.persist(user_id, self.board_name(ctx), saved, cleared))
            self.saving.add(task)
            task.add_done_callback(self.saving.discard)

    async def persist(self, user_id: int, name: str, saved: dict | None, cleared: list[tuple[int, int]]) -> None:
        """Written off the game path, one player at a time and in the order the changes happened"""
        try:
            async with self.lock_for(user_id):
                group = self.config.user_from_id(user_id)
                entry = await group.all()
                now = time.time()
                for stage, moves in cleared:
                    entry, _ = scores.record(entry, stage, moves, name, now)
                entry["run"] = saved or {}
                await group.set(entry)
        except Exception as e:
            log.error("Couldn't save a Bloxorz run for user %s", user_id, exc_info=e)

    # ---------- The leaderboard ----------

    async def leaderboard(self, ctx: t.Any, data: t.Any) -> dict:
        """Stage 0 ranks every player across all stages, 1 to 33 ranks one stage"""
        stage = data.get("stage") if isinstance(data, dict) else None
        if type(stage) is not int or not 0 <= stage <= len(STAGES):
            return {"top": [], "you": None}
        users = await self.config.all_users()
        if stage == 0:
            return scores.rank_all(users, ctx.author.id)
        return scores.rank_stage(users, stage, ctx.author.id)
