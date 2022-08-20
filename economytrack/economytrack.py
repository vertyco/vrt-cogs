import asyncio
import logging
from datetime import datetime

from discord.ext import tasks
from redbot.core import commands, Config, bank
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils import AsyncIter

from economytrack.abc import CompositeMetaClass
from economytrack.commands import EconomyTrackComands
from economytrack.graph import PlotGraph

log = logging.getLogger("red.vrt.economytrack")
_ = Translator("EconomyTrack", __file__)


# Credits to Vexed01 for having a great reference cog for some of the logic that went into this!
# Vex-Cogs - https://github.com/Vexed01/Vex-Cogs - (StatTrack)


@cog_i18n(_)
class EconomyTrack(commands.Cog, EconomyTrackComands, PlotGraph, metaclass=CompositeMetaClass):
    """Track your economy's total balance over time"""
    __author__ = "Vertyco"
    __version__ = "0.0.1"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\n" \
               f"Cog Version: {self.__version__}\n" \
               f"Author: {self.__author__}\n"
        return _(info)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=117, force_registration=True)
        default_global = {"max_points": 43200, "data": []}
        default_guild = {"timezone": "UTC", "data": []}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.bank_loop.start()

    def cog_unload(self):
        self.bank_loop.cancel()

    @tasks.loop(minutes=1)
    async def bank_loop(self):
        is_global = await bank.is_global()
        max_points = await self.config.max_points()
        if max_points == 0:  # 0 is no limit
            max_points = 52560000  # 100 years is plenty
        now = datetime.now().replace(microsecond=0, second=0).timestamp()
        if is_global:
            members = await bank._config.all_users()
            total = sum(value["balance"] for value in members.values())
            async with self.config.data() as data:
                data.append((now, total))
                if len(data) > max_points:
                    del data[0:len(data) - max_points]
        else:
            async for guild in AsyncIter(self.bot.guilds):
                members = await bank._config.all_members(guild)
                total = sum(value["balance"] for value in members.values())
                async with self.config.guild(guild).data() as data:
                    data.append((now, total))
                    if len(data) > max_points:
                        del data[0:len(data) - max_points]

    @bank_loop.before_loop
    async def before_bank_loop(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(60)
        log.info(_("EconomyTrack Ready"))
