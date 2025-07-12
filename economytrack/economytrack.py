import asyncio
import logging
from datetime import datetime
from time import monotonic

import discord
from discord.ext import tasks
from redbot.core import Config, bank, commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter

from economytrack.abc import CompositeMetaClass
from economytrack.commands import EconomyTrackCommands
from economytrack.graph import PlotGraph

log = logging.getLogger("red.vrt.economytrack")


# Credits to Vexed01 for having a great reference cog for some of the logic that went into this!
# Vex-Cogs - https://github.com/Vexed01/Vex-Cogs - (StatTrack)


class EconomyTrack(commands.Cog, EconomyTrackCommands, PlotGraph, metaclass=CompositeMetaClass):
    """
    Track your economy's total balance over time

    Also track you server's member count!
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "0.6.0"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}\n"
        return info

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=117, force_registration=True)
        default_global = {"max_points": 21600, "data": []}
        default_guild = {
            "timezone": "UTC",
            "data": [],
            "enabled": False,
            "member_data": [],
            "member_tracking": False,
        }
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)
        self.looptime = None
        self.bank_loop.start()

    def cog_unload(self):
        self.bank_loop.cancel()

    @tasks.loop(minutes=2)
    async def bank_loop(self):
        start = monotonic()
        is_global = await bank.is_global()
        max_points = await self.config.max_points()
        if max_points == 0:  # 0 is no limit
            max_points = 26280000  # 100 years is plenty
        now = datetime.now().replace(microsecond=0, second=0).timestamp()
        if is_global:
            total = await self.get_total_bal()
            async with self.config.data() as data:
                data.append((now, total))
                if len(data) > max_points:
                    del data[0 : len(data) - max_points]
        else:
            async for guild in AsyncIter(self.bot.guilds):
                if not await self.config.guild(guild).enabled():
                    continue
                total = await self.get_total_bal(guild)
                async with self.config.guild(guild).data() as data:
                    data.append((now, total))
                    if len(data) > max_points:
                        del data[0 : len(data) - max_points]

        async for guild in AsyncIter(self.bot.guilds):
            if not await self.config.guild(guild).member_tracking():
                continue
            members = guild.member_count
            async with self.config.guild(guild).member_data() as data:
                data.append((now, members))
                if len(data) > max_points:
                    del data[0 : len(data) - max_points]

        iter_time = round((monotonic() - start) * 1000)
        avg_iter = self.looptime
        if avg_iter is None:
            self.looptime = iter_time
        else:
            self.looptime = round((avg_iter + iter_time) / 2)

    @staticmethod
    async def get_total_bal(guild: discord.guild = None) -> int:
        is_global = await bank.is_global()
        if is_global:
            members = await bank._config.all_users()
        else:
            members = await bank._config.all_members(guild)
        total = sum(value["balance"] for value in members.values())
        return int(total)

    @bank_loop.before_loop
    async def before_bank_loop(self):
        await self.bot.wait_until_red_ready()
        await asyncio.sleep(120)
        log.info("EconomyTrack Ready")
