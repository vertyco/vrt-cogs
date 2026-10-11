import asyncio
import logging
import random
import time
import typing as t
from collections import defaultdict
from pathlib import Path

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands.farmcord import CREDIT_LINE, FarmCordCommands
from .common.actions import Actions
from .common.payouts import Payouts
from .common.store import Store
from .db.tables import TABLES
from .engine import engine
from .views.play import PlayView

log = logging.getLogger("red.vrt.farmcord")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]
# How long a data deletion request waits for the database to open
DELETE_WAIT = 60


class FarmCord(FarmCordCommands, Actions, commands.Cog, metaclass=CompositeMetaClass):
    """
    A small FarmVille for ActivityHub: grow crops through the seasons, raise and breed animals, and build up your farm.

    One farm per player, shared by every server and DMs, with a global leaderboard.

    Game design by Vainne: https://github.com/Atuelliss
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.store = Store()
        self.config = Config.get_conf(self, identifier=2026101001, force_registration=True)
        self.config.register_global(payouts={})
        self.config.register_guild(payouts={})
        self.config.register_user(cashed={})
        self.config.register_member(cashed={})
        self.payouts = Payouts(self.config)
        # The bot keeps the clock and rolls every random result. Tests swap in a clock and rolls of their own
        self.clock = time.time
        self.rng = random.SystemRandom()
        self.ready = asyncio.Event()
        # One lock per player: every action loads, changes and saves the whole farm, so two at once would undo
        # each other
        self.locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.starting: asyncio.Task | None = None
        self.play_view: PlayView | None = None

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}\n{}".format(self.__version__, self.__author__, CREDIT_LINE)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        # The payout ledger lives in Config, which needs no database
        await self.config.user_from_id(user_id).clear()
        for guild_id, members in (await self.config.all_members()).items():
            if user_id in members:
                await self.config.member_from_ids(guild_id, user_id).clear()
        try:
            await asyncio.wait_for(self.ready.wait(), DELETE_WAIT)
        except asyncio.TimeoutError as e:
            log.error("FarmCord's database isn't open, so user %s's farm couldn't be deleted: %r", user_id, e)
            return
        # Under the player's lock, so an action already running can't save the farm back after it is gone
        async with self.locks[user_id]:
            await self.store.delete_user(user_id)

    async def cog_load(self) -> None:
        self.play_view = PlayView(self)
        # Play buttons posted before a restart work again once the view is added back
        self.bot.add_view(self.play_view)
        self.starting = asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        logging.getLogger("aiosqlite").setLevel(logging.INFO)
        try:
            await engine.register_cog(self, TABLES, trace=True)
        except Exception as e:
            log.exception("FarmCord's database couldn't start, so the farms stay closed", exc_info=e)
            return
        self.ready.set()
        log.info("FarmCord is open")

    async def cog_unload(self) -> None:
        # Page actions are refused from here on
        self.ready.clear()
        if self.starting is not None and not self.starting.done():
            self.starting.cancel()
            await asyncio.wait({self.starting}, timeout=5)
        if self.play_view is not None:
            self.play_view.stop()

    async def activityhub_game(self) -> dict:
        return {
            "key": "farmcord",
            "name": "FarmCord",
            "description": "Grow crops, raise animals and build your farm",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.png",
            "thumbnail": "thumb.png",
            "actions": self.action_handlers(),
        }
