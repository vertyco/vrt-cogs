import asyncio
import logging
import random
import typing as t
from pathlib import Path

from redbot.core import commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands.casino import CasinoCommands
from .commands.casinoset import CasinoSetCommands
from .common.actions import Actions
from .common.catalog import CREDIT
from .common.info import casino_info, me
from .common.memberships import Updater
from .common.money import Money, RedBank
from .common.rounds import TABLE_TYPES
from .common.sockets import Sockets
from .common.store import Store
from .common.table import Floor
from .db.tables import TABLES
from .engine import engine
from .views.play import PlayView

log = logging.getLogger("red.vrt.casino")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]
# How long a data deletion request waits for the database to open
DELETE_WAIT = 60


class Casino(CasinoCommands, CasinoSetCommands, Actions, Sockets, commands.Cog, metaclass=CompositeMetaClass):
    """
    Blackjack, craps, war and six more casino games for ActivityHub, on a Classic Vegas casino floor.

    Rebuilt for ActivityHub from Redjumpman's Casino: https://github.com/Redjumpman/Jumper-Plugins
    """

    __author__ = "Vertyco"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.store = Store()
        self.bank = RedBank()
        self.money = Money(self.store, self.bank)
        self.rng = random.SystemRandom()
        self.table_types = TABLE_TYPES
        # One floor per Activity window, keyed by the window's instance id
        self.floors: dict[str, Floor] = {}
        self.ready = asyncio.Event()
        self.updater = Updater(bot, self.store, self.bank, self.refresh_players)
        self.starting: asyncio.Task | None = None
        self.updating: asyncio.Task | None = None
        self.play_view: PlayView | None = None

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}\n{}".format(self.__version__, self.__author__, CREDIT)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: RequestType, user_id: int):
        try:
            await asyncio.wait_for(self.ready.wait(), DELETE_WAIT)
        except asyncio.TimeoutError as e:
            log.error("The casino's database isn't open, so user %s's data couldn't be deleted: %r", user_id, e)
            return
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
            log.exception("The casino's database couldn't start, so the casino stays closed", exc_info=e)
            return
        self.ready.set()
        self.updating = asyncio.create_task(self.updater.run_forever())
        log.info("Casino is open")

    async def stop_task(self, task: asyncio.Task | None, patience: float) -> None:
        """Waits up to patience seconds for the task, then cancels it and waits again. Never raises"""
        if task is None or task.done():
            return
        finished, pending = await asyncio.wait({task}, timeout=patience)
        if pending:
            log.debug("%s didn't stop in %s seconds, cancelling it", task.get_name(), patience)
            task.cancel()
            await asyncio.wait({task}, timeout=5)

    async def cog_unload(self) -> None:
        # Joins, messages and page actions are refused from here on, so nothing new starts while the floors close
        self.ready.clear()
        self.updater.stopping.set()
        try:
            # Every bet still in play is refunded
            for floor in list(self.floors.values()):
                try:
                    await floor.close()
                except Exception as e:
                    log.exception("Couldn't close a floor while unloading", exc_info=e)
            if self.starting is not None and not self.starting.done():
                self.starting.cancel()
            await self.stop_task(self.starting, 5)
            # The updater stops between passes, so it never leaves a database write half done
            await self.stop_task(self.updating, 10)
        finally:
            if self.play_view is not None:
                self.play_view.stop()

    async def activityhub_game(self) -> dict:
        return {
            "key": "casino",
            "name": "Casino",
            "description": "Blackjack, craps, war and six more, on a Vegas floor",
            "web_dir": Path(__file__).parent / "web",
            "icon": "icon.png",
            "thumbnail": "thumb.jpg",
            "actions": self.action_handlers(),
            "socket": {"join": self.join, "message": self.message, "leave": self.leave},
        }

    # ---------- Keeping open pages up to date ----------

    async def send_me(self, floor: Floor, member) -> None:
        scope = await floor.scope()
        update = await me(self.store, self.money, scope, member)
        for conn in floor.conns_of(member.id):
            await conn.send(update)

    async def refresh(self, scope: int | None = None) -> None:
        """After a settings change, every open page in that scope (or every page) gets the new settings and its
        player's facts, which a membership change may have moved"""
        for floor in list(self.floors.values()):
            floor_scope = await floor.scope()
            if scope is not None and floor_scope != scope:
                continue
            await floor.room.broadcast({"t": "casino", "casino": await casino_info(self.store, floor_scope)})
            for conn in list(floor.where):
                await conn.send(await me(self.store, self.money, floor_scope, conn.ctx.author))

    async def refresh_players(self, scope: int, user_ids: set[int]) -> None:
        """After the membership updater moved these players, their open pages in that scope get their new facts"""
        for floor in list(self.floors.values()):
            if await floor.scope() != scope:
                continue
            for conn in list(floor.where):
                if conn.ctx.author.id in user_ids:
                    await conn.send(await me(self.store, self.money, scope, conn.ctx.author))

    def floor_done(self, floor: Floor) -> None:
        if floor.idle() and self.floors.get(floor.room.instance_id) is floor:
            del self.floors[floor.room.instance_id]
