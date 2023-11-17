import asyncio
import logging
from datetime import datetime, timedelta
from time import monotonic

import discord
import pandas as pd
import pytz
from discord.ext import tasks
from redbot.core import Config, bank, commands
from redbot.core.bot import Red
from redbot.core.utils import AsyncIter
from redbot.core.utils.chat_formatting import box, humanize_number, humanize_timedelta

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

    __author__ = "Vertyco"
    __version__ = "0.5.5"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        info = f"{helpcmd}\n" f"Cog Version: {self.__version__}\n" f"Author: {self.__author__}\n"
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

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        schema1 = {
            "name": "get_member_count_info",
            "description": "Get member stats of the current server over a period of time",
            "parameters": {
                "type": "object",
                "properties": {
                    "timespan": {
                        "type": "string",
                        "description": "span of time to pull data for, defaults to one day, 'all' can be specified to pull history for all time. Examples: 3w2d, 5d, 20h",
                    },
                },
            },
        }
        schema2 = {
            "name": "get_economy_info",
            "description": "Get total amount of currency for the current guild, along with bank info and economy stats",
            "parameters": {
                "type": "object",
                "properties": {
                    "timespan": {
                        "type": "string",
                        "description": "span of time to pull data for, defaults to one day, 'all' can be specified to pull history for all time. Examples: 3w2d, 5d, 20h",
                    },
                },
            },
        }
        await cog.register_functions("EconomyTrack", [schema1, schema2])

    async def get_member_count_info(self, guild: discord.Guild, timespan: str = "1d", *args, **kwargs) -> str:
        if timespan.lower() == "all":
            delta = timedelta(days=36500)
        else:
            delta = commands.parse_timedelta(timespan, minimum=timedelta(hours=1))
            if delta is None:
                delta = timedelta(hours=1)

        data = await self.config.guild(guild).member_data()
        if len(data) < 2:
            return "There is not enough data collected. Try again later."

        timezone = await self.config.guild(guild).timezone()
        now = datetime.now().astimezone(tz=pytz.timezone(timezone))
        start = now - delta
        columns = ["ts", "total"]
        rows = [i for i in data]
        for i in rows:
            i[0] = datetime.fromtimestamp(i[0]).astimezone(tz=pytz.timezone(timezone))
        df = pd.DataFrame(rows, columns=columns)
        df = df.set_index(["ts"])
        df = df[~df.index.duplicated(keep="first")]  # Remove duplicate indexes
        mask = (df.index > start) & (df.index <= now)
        df = df.loc[mask]
        df = pd.DataFrame(df)

        if df.empty or len(df.values) < 2:  # In case there is data but it is old
            return "There is not enough data collected. Try again later."

        if timespan.lower() == "all":
            alltime = humanize_timedelta(seconds=len(data) * 60)
            reply = f"Total member count for all time ({alltime})\n"
        else:
            delta: timedelta = df.index[-1] - df.index[0]
            reply = f"Total member count over the last {humanize_timedelta(timedelta=delta)}\n"

        lowest = df.min().total
        highest = df.max().total
        avg = df.mean().total
        current = df.values[-1][0]

        reply += f"`DataPoints: `{humanize_number(len(df.values))}\n"

        reply += (
            "Statistics\n"
            f"`Current: `{humanize_number(current)}\n"
            f"`Average: `{humanize_number(round(avg))}\n"
            f"`Highest: `{humanize_number(highest)}\n"
            f"`Lowest:  `{humanize_number(lowest)}\n"
            f"`Diff:    `{humanize_number(highest - lowest)}\n"
        )

        first = df.values[0][0]
        diff = "+" if current > first else "-"
        field = f"{diff} {humanize_number(abs(current - first))}"
        reply += f"Since <t:{int(df.index[0].timestamp())}:D>\n{box(field, 'diff')}"
        return reply

    async def get_economy_info(self, guild: discord.Guild, timespan: str = "1d", *args, **kwargs) -> str:
        if timespan.lower() == "all":
            delta = timedelta(days=36500)
        else:
            delta = commands.parse_timedelta(timespan, minimum=timedelta(hours=1))
            if delta is None:
                delta = timedelta(hours=1)

        is_global = await bank.is_global()
        currency_name = await bank.get_currency_name(guild)
        bank_name = await bank.get_bank_name(guild)
        if is_global:
            data = await self.config.data()
        else:
            data = await self.config.guild(guild).data()

        if len(data) < 2:
            return "There is not enough data collected. Try again later."

        timezone = await self.config.guild(guild).timezone()
        now = datetime.now().astimezone(tz=pytz.timezone(timezone))
        start = now - delta
        columns = ["ts", "total"]
        rows = [i for i in data]
        for i in rows:
            i[0] = datetime.fromtimestamp(i[0]).astimezone(tz=pytz.timezone(timezone))
        df = pd.DataFrame(rows, columns=columns)
        df = df.set_index(["ts"])
        df = df[~df.index.duplicated(keep="first")]  # Remove duplicate indexes
        mask = (df.index > start) & (df.index <= now)
        df = df.loc[mask]
        df = pd.DataFrame(df)

        if df.empty or len(df.values) < 2:  # In case there is data but it is old
            return "There is not enough data collectedTry again later."

        if timespan.lower() == "all":
            alltime = humanize_timedelta(seconds=len(data) * 60)
            reply = f"Total economy balance for all time ({alltime})"
        else:
            delta: timedelta = df.index[-1] - df.index[0]
            reply = f"Total economy balance over the last {humanize_timedelta(timedelta=delta)}"

        lowest = df.min().total
        highest = df.max().total
        avg = df.mean().total
        current = df.values[-1][0]

        reply += (
            f"`DataPoints: `{humanize_number(len(df.values))}\n"
            f"`BankName:   `{bank_name}\n"
            f"`Currency:   `{currency_name}"
        )

        reply += (
            "Statistics\n"
            f"`Current: `{humanize_number(current)}\n"
            f"`Average: `{humanize_number(round(avg))}\n"
            f"`Highest: `{humanize_number(highest)}\n"
            f"`Lowest:  `{humanize_number(lowest)}\n"
            f"`Diff:    `{humanize_number(highest - lowest)}\n"
        )

        first = df.values[0][0]
        diff = "+" if current > first else "-"
        field = f"{diff} {humanize_number(abs(current - first))}"
        reply += f"Since <t:{int(df.index[0].timestamp())}:D>\n{box(field, 'diff')}"
        return reply
