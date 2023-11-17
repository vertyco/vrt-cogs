import datetime

import discord
import pandas as pd
import pytz
from discord.ext.commands.cooldowns import BucketType
from rapidfuzz import fuzz
from redbot.core import bank, commands
from redbot.core.commands import parse_timedelta
from redbot.core.utils.chat_formatting import box, humanize_number, humanize_timedelta

from economytrack.abc import MixinMeta


class EconomyTrackCommands(MixinMeta):
    @commands.group(aliases=["ecotrack"])
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def economytrack(self, ctx: commands.Context):
        """Configure EconomyTrack"""

    @economytrack.command()
    @commands.guildowner()
    @commands.guild_only()
    async def togglebanktrack(self, ctx: commands.Context):
        """Enable/Disable economy tracking for this server"""
        async with self.config.guild(ctx.guild).all() as conf:
            if conf["enabled"]:
                conf["enabled"] = False
                await ctx.send("Economy tracking has been **Disabled**")
            else:
                conf["enabled"] = True
                await ctx.send("Economy tracking has been **Enabled**")

    @economytrack.command()
    @commands.guildowner()
    @commands.guild_only()
    async def togglemembertrack(self, ctx: commands.Context):
        """Enable/Disable member tracking for this server"""
        async with self.config.guild(ctx.guild).all() as conf:
            if conf["member_tracking"]:
                conf["member_tracking"] = False
                await ctx.send("Member tracking has been **Disabled**")
            else:
                conf["member_tracking"] = True
                await ctx.send("Member tracking has been **Enabled**")

    @economytrack.command()
    @commands.is_owner()
    async def maxpoints(self, ctx: commands.Context, max_points: int):
        """
        Set the max amount of data points the bot will store

        **Arguments**
        `<max_points>` Maximum amount of data points to store

        The loop runs every 2 minutes, so 720 points equals 1 day
        The default is 21600 (30 days)
        Set to 0 to store data indefinitely (Not Recommended)
        """
        await self.config.max_points.set(max_points)
        await ctx.tick()

    @economytrack.command()
    async def timezone(self, ctx: commands.Context, timezone: str):
        """
        Set your desired timezone for the graph

        **Arguments**
        `<timezone>` A string representing a valid timezone

        **Example:** `[p]ecotrack timezone US/Eastern`

        Use this command without the argument to get a huge list of valid timezones.
        """
        timezone = timezone.lower()
        try:
            tz = pytz.timezone(timezone)
        except pytz.UnknownTimeZoneError:
            likely_match = sorted(pytz.common_timezones, key=lambda x: fuzz.ratio(timezone, x.lower()), reverse=True)[0]
            return await ctx.send(f"Invalid Timezone, did you mean `{likely_match}`?")
        time = datetime.datetime.now(tz).strftime("%I:%M %p")  # Convert to 12-hour format
        await ctx.send(f"Timezone set to **{timezone}** (`{time}`)")
        await self.config.guild(ctx.guild).timezone.set(timezone)

    @economytrack.command()
    @commands.bot_has_permissions(embed_links=True)
    async def view(self, ctx: commands.Context):
        """View EconomyTrack Settings"""
        max_points = await self.config.max_points()
        is_global = await bank.is_global()
        conf = await self.config.guild(ctx.guild).all()
        timezone = conf["timezone"]
        enabled = conf["enabled"]
        if is_global:
            data = await self.config.data()
            points = len(data)
        else:
            data = await self.config.guild(ctx.guild).data()
            points = len(data)
        avg_iter = self.looptime if self.looptime else "(N/A)"
        ptime = humanize_timedelta(seconds=int(points * 60))
        mptime = humanize_timedelta(seconds=int(max_points * 60))
        desc = (
            f"`Enabled:    `{enabled}\n"
            f"`Timezone:   `{timezone}\n"
            f"`Max Points: `{humanize_number(max_points)} ({mptime})\n"
            f"`Collected:  `{humanize_number(points)} ({ptime if ptime else 'None'})\n"
            f"`LoopTime:   `{avg_iter}ms"
        )
        embed = discord.Embed(title="EconomyTrack Settings", description=desc, color=ctx.author.color)
        memtime = humanize_timedelta(seconds=len(conf["member_data"]) * 60)
        embed.add_field(
            name="Member Tracking",
            value=(
                f"`Enabled:   `{conf['member_tracking']}\n"
                f"`Collected: `{humanize_number(len(conf['member_data']))} ({memtime if memtime else 'None'})"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guildowner()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def remoutliers(self, ctx: commands.Context, max_value: int, datatype: str = "bank"):
        """
        Cleanup data above a certain total economy balance

        **Arguments**
        datatype: either `bank` or `member`
        """
        if datatype.lower() in ["b", "bank", "bnk"]:
            banktype = True
        else:
            banktype = False

        is_global = await bank.is_global()

        if banktype:
            if is_global:
                data = await self.config.data()
            else:
                data = await self.config.guild(ctx.guild).data()
        else:
            data = await self.config.guild(ctx.guild).member_data()

        if len(data) < 10:
            embed = discord.Embed(
                description="There is not enough data collected. Try again later.",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        newrows = [i for i in data if i[1] <= max_value]
        deleted = len(data) - len(newrows)
        if not deleted:
            return await ctx.send("No data to delete")

        async with ctx.typing():
            if banktype:
                if is_global:
                    await self.config.data.set(newrows)
                else:
                    await self.config.guild(ctx.guild).data.set(newrows)
            else:
                await self.config.guild(ctx.guild).member_data.set(newrows)
            await ctx.send("Deleted all data points above " + str(max_value))

    @commands.command(aliases=["bgraph"])
    @commands.cooldown(5, 60.0, BucketType.user)
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def bankgraph(self, ctx: commands.Context, timespan: str = "1d"):
        """
        View bank status over a period of time.
        **Arguments**
        `<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.
        Must be at least 1 hour.
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
        currency_name = await bank.get_currency_name(ctx.guild)
        bank_name = await bank.get_bank_name(ctx.guild)
        if is_global:
            data = await self.config.data()
        else:
            data = await self.config.guild(ctx.guild).data()
        if len(data) < 10:
            embed = discord.Embed(
                description="There is not enough data collected to generate a graph right now. Try again later.",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)
        timezone = await self.config.guild(ctx.guild).timezone()
        now = datetime.datetime.now().astimezone(tz=pytz.timezone(timezone))
        start = now - delta
        columns = ["ts", "total"]
        rows = [i for i in data]
        for i in rows:
            i[0] = datetime.datetime.fromtimestamp(i[0]).astimezone(tz=pytz.timezone(timezone))
        df = pd.DataFrame(rows, columns=columns)
        df = df.set_index(["ts"])
        df = df[~df.index.duplicated(keep="first")]  # Remove duplicate indexes
        mask = (df.index > start) & (df.index <= now)
        df = df.loc[mask]
        df = pd.DataFrame(df)

        if df.empty or len(df.values) < 10:  # In case there is data but it is old
            embed = discord.Embed(
                description="There is not enough data collected to generate a graph right now. Try again later.",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        delta: datetime.timedelta = df.index[-1] - df.index[0]
        if timespan.lower() == "all":
            title = f"Total economy balance for all time ({humanize_timedelta(timedelta=delta)})"
        else:
            title = f"Total economy balance over the last {humanize_timedelta(timedelta=delta)}"

        lowest = df.min().total
        highest = df.max().total
        avg = df.mean().total
        current = df.values[-1][0]

        desc = (
            f"`DataPoints: `{humanize_number(len(df.values))}\n"
            f"`BankName:   `{bank_name}\n"
            f"`Currency:   `{currency_name}"
        )

        field = (
            f"`Current: `{humanize_number(current)}\n"
            f"`Average: `{humanize_number(round(avg))}\n"
            f"`Highest: `{humanize_number(highest)}\n"
            f"`Lowest:  `{humanize_number(lowest)}\n"
            f"`Diff:    `{humanize_number(highest - lowest)}"
        )

        first = df.values[0][0]
        diff = "+" if current > first else "-"
        field2 = f"{diff} {humanize_number(abs(current - first))}"

        embed = discord.Embed(title=title, description=desc, color=ctx.author.color)
        embed.add_field(name="Statistics", value=field)
        embed.add_field(
            name="Change",
            value=f"Since <t:{int(df.index[0].timestamp())}:D>\n{box(field2, 'diff')}",
        )

        embed.set_image(url="attachment://plot.png")
        embed.set_footer(text=f"Timezone: {timezone}")
        async with ctx.typing():
            file = await self.get_plot(df, "Total Economy Credits")
        await ctx.send(embed=embed, file=file)

    @commands.command(aliases=["memgraph"])
    @commands.cooldown(5, 60.0, BucketType.user)
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True, attach_files=True)
    async def membergraph(self, ctx: commands.Context, timespan: str = "1d"):
        """
        View member count over a period of time.
        **Arguments**
        `<timespan>` How long to look for, or `all` for all-time data. Defaults to 1 day.
        Must be at least 1 hour.
        **Examples:**
            - `[p]membergraph 3w2d`
            - `[p]membergraph 5d`
            - `[p]membergraph all`
        """
        if timespan.lower() == "all":
            delta = datetime.timedelta(days=36500)
        else:
            delta = parse_timedelta(timespan, minimum=datetime.timedelta(hours=1))
            if delta is None:
                delta = datetime.timedelta(hours=1)

        data = await self.config.guild(ctx.guild).member_data()
        if len(data) < 10:
            embed = discord.Embed(
                description="There is not enough data collected to generate a graph right now. Try again later.",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)
        timezone = await self.config.guild(ctx.guild).timezone()
        now = datetime.datetime.now().astimezone(tz=pytz.timezone(timezone))
        start = now - delta
        columns = ["ts", "total"]
        rows = [i for i in data]
        for i in rows:
            i[0] = datetime.datetime.fromtimestamp(i[0]).astimezone(tz=pytz.timezone(timezone))
        df = pd.DataFrame(rows, columns=columns)
        df = df.set_index(["ts"])
        df = df[~df.index.duplicated(keep="first")]  # Remove duplicate indexes
        mask = (df.index > start) & (df.index <= now)
        df = df.loc[mask]
        df = pd.DataFrame(df)

        if df.empty or len(df.values) < 10:  # In case there is data but it is old
            embed = discord.Embed(
                description="There is not enough data collected to generate a graph right now. Try again later.",
                color=discord.Color.red(),
            )
            return await ctx.send(embed=embed)

        delta: datetime.timedelta = df.index[-1] - df.index[0]
        if timespan.lower() == "all":
            title = f"Total member count for all time ({humanize_timedelta(timedelta=delta)})"
        else:
            title = f"Total member count over the last {humanize_timedelta(timedelta=delta)}"

        lowest = df.min().total
        highest = df.max().total
        avg = df.mean().total
        current = df.values[-1][0]

        desc = f"`DataPoints: `{humanize_number(len(df.values))}"

        field = (
            f"`Current: `{humanize_number(current)}\n"
            f"`Average: `{humanize_number(round(avg))}\n"
            f"`Highest: `{humanize_number(highest)}\n"
            f"`Lowest:  `{humanize_number(lowest)}\n"
            f"`Diff:    `{humanize_number(highest - lowest)}"
        )

        first = df.values[0][0]
        diff = "+" if current > first else "-"
        field2 = f"{diff} {humanize_number(abs(current - first))}"

        embed = discord.Embed(title=title, description=desc, color=ctx.author.color)
        embed.add_field(name="Statistics", value=field)
        embed.add_field(
            name="Change",
            value=f"Since <t:{int(df.index[0].timestamp())}:D>\n{box(field2, 'diff')}",
        )

        embed.set_image(url="attachment://plot.png")
        embed.set_footer(text=f"Timezone: {timezone}")
        async with ctx.typing():
            file = await self.get_plot(df, "Member Count")
        await ctx.send(embed=embed, file=file)
