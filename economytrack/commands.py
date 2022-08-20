import datetime

import discord
import pandas as pd
import pytz
from discord.ext.commands.cooldowns import BucketType
from redbot.core import commands, bank
from redbot.core.commands import parse_timedelta
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import (
    box,
    humanize_list,
    humanize_number,
    humanize_timedelta,
    pagify,
)

from economytrack.abc import MixinMeta

_ = Translator("EconomyTrackCommands", __file__)


@cog_i18n(_)
class EconomyTrackComands(MixinMeta):
    @commands.group(aliases=["ecotrack"])
    @commands.admin()
    async def economytrack(self, ctx: commands.Context):
        """Configure EconomyTrack"""

    @economytrack.command()
    @commands.is_owner()
    async def maxpoints(self, ctx: commands.Context, max_points: int):
        """
        Set the max amount of data points the bot will store

        The loop runs every minute, so 1440 points equals 1 day
        The default is 43200 (30 days)
        Set to 0 to store data indefinitely (Not Recommended)
        """
        await self.config.max_points.set(max_points)
        await ctx.tick()

    @economytrack.command()
    async def timezone(self, ctx: commands.Context, timezone: str = None):
        """Set your desired timezone for the graph"""
        tzs = pytz.common_timezones
        timezones = humanize_list(tzs)
        command = f"`{ctx.prefix}ecotrack timezone US/Eastern`"
        text = _(f"Use one of these timezones with this command\n") + _("Example: ") + command
        if not timezone:
            embed = discord.Embed(
                title=_("Valid Timezones"),
                description=text,
                color=ctx.author.color
            )
            await ctx.send(embed=embed)
            for p in pagify(timezones):
                await ctx.send(embed=discord.Embed(description=box(p)))
            return
        if timezone not in tzs:
            embed = discord.Embed(
                title=_("Invalid Timezone!"),
                description=text,
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            for p in pagify(timezones):
                await ctx.send(embed=discord.Embed(description=box(p)))
            return
        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.tick()

    @economytrack.command()
    async def view(self, ctx: commands.Context):
        """View EconomyTrack Settings"""
        max_points = await self.config.max_points()
        is_global = await bank.is_global()
        if is_global:
            data = await self.config.data()
            points = len(data)
        else:
            data = await self.config.guild(ctx.guild).data()
            points = len(data)
        ptime = humanize_timedelta(seconds=int(points * 60))
        mptime = humanize_timedelta(seconds=int(max_points * 60))
        timezone = await self.config.guild(ctx.guild).timezone()
        desc = _(f"`Max Points: `{humanize_number(max_points)} ({mptime})\n"
                 f"`Collected:  `{humanize_number(points)} ({ptime if ptime else 'None'})\n"
                 f"`Timezone:   `{timezone}")
        embed = discord.Embed(
            title=_("EconomyTrack Settings"),
            description=desc,
            color=ctx.author.color
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["bgraph"])
    @commands.cooldown(5, 60.0, BucketType.user)
    async def bankgraph(self, ctx: commands.Context, timespan: str = "1d"):
        """
        View bank status over a period of time.
        **Arguments**
        `<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day. Must be
        at least 1 hour.
        **Examples:**
            - `[p]bankgraph 3w2d`
            - `[p]bankgraph 5d`
            - `[p]bankgraph all`
        """
        if timespan.lower() == "all":
            delta = datetime.timedelta(days=36500)
        else:
            delta = parse_timedelta(timespan, minimum=datetime.timedelta(hours=1))
            if delta is None:
                delta = datetime.timedelta(hours=1)
        is_global = await bank.is_global()
        if is_global:
            data = await self.config.data()
            currency_name = "Credits"
        else:
            data = await self.config.guild(ctx.guild).data()
            currency_name = await bank.get_currency_name(ctx.guild)
        if len(data) < 10:
            embed = discord.Embed(
                description=_("There is not enough data collected to generate a graph right now. Try again later."),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)
        timezone = await self.config.guild(ctx.guild).timezone()
        now = datetime.datetime.now().replace(microsecond=0, second=0).astimezone(tz=pytz.timezone(timezone))
        start = now.timestamp() - delta.total_seconds()
        frames = []
        for ts_raw, total in data:
            if ts_raw < start:
                continue
            timestamp = datetime.datetime.fromtimestamp(ts_raw).astimezone(tz=pytz.timezone(timezone))
            df = pd.DataFrame([total], index=[timestamp])
            frames.append(df)
        df = pd.concat(frames)

        if timespan.lower() == "all":
            title = f"{currency_name} spent for all time"
        else:
            title = f"{currency_name} spend for the last {humanize_timedelta(timedelta=delta)}"

        desc = _(f"Current timezone is **{timezone}**")
        embed = discord.Embed(
            title=_(title),
            description=desc,
            color=ctx.author.color
        )
        embed.set_image(url="attachment://plot.png")

        file = await self.get_plot(df)
        await ctx.send(embed=embed, file=file)
