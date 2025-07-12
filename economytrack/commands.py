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
    async def remoutliers(
        self, ctx: commands.Context, min_value: int = None, max_value: int = None, datatype: str = "bank"
    ):
        """
        Cleanup data that falls outside a specified range

        **Arguments**
        `[min_value]` - Minimum value to keep (optional)
        `[max_value]` - Maximum value to keep (optional)
        `[datatype]` - Either `bank` or `member` (defaults to bank)

        At least one of min_value or max_value must be provided.

        **Examples:**
        `[p]remoutliers 0 50000 bank` - Remove bank points outside 0-50000 range
        `[p]remoutliers 500 10000 member` - Remove member counts outside 500-10000 range
        `[p]remoutliers None 8000 member` - Remove only data points above 8000 members
        `[p]remoutliers 5000 None member` - Remove only data points below 5000 members
        """
        # Check if at least one threshold is provided
        if min_value is None and max_value is None:
            return await ctx.send("You must provide at least one threshold (min_value or max_value).")

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

        # Filter data based on provided thresholds
        original_count = len(data)
        if min_value is not None and max_value is not None:
            newrows = [i for i in data if i[1] and min_value <= i[1] <= max_value]
            range_str = f"between {min_value} and {max_value}"
        elif min_value is not None:
            newrows = [i for i in data if i[1] and i[1] >= min_value]
            range_str = f"below {min_value}"
        else:  # max_value is not None
            newrows = [i for i in data if i[1] and i[1] <= max_value]
            range_str = f"above {max_value}"

        deleted = original_count - len(newrows)
        if not deleted:
            return await ctx.send("No data points found outside the specified range.")

        async with ctx.typing():
            if banktype:
                if is_global:
                    await self.config.data.set(newrows)
                else:
                    await self.config.guild(ctx.guild).data.set(newrows)
            else:
                await self.config.guild(ctx.guild).member_data.set(newrows)

            data_type_str = "bank balance" if banktype else "member count"
            await ctx.send(f"Deleted {deleted} data points with {data_type_str} {range_str}")

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
            f"`DataPoints: `{humanize_number(len(df.values))}\n`BankName:   `{bank_name}\n`Currency:   `{currency_name}"
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

    @commands.command()
    @commands.guildowner()
    @commands.guild_only()
    @commands.bot_has_permissions(embed_links=True)
    async def autoremoutliers(
        self,
        ctx: commands.Context,
        confirm: bool,
        datatype: str = "bank",
        multiplier: float = 1.5,
    ):
        """
        Automatically detect and remove outliers in your data using statistical methods

        **Arguments**
        `[datatype]` - Either `bank` or `member` (defaults to bank)
        `[multiplier]` - IQR multiplier for outlier detection sensitivity (default: 1.5)
            - Higher values = more lenient (keeps more data)
            - Lower values = more strict (removes more outliers)
        `[confirm]` - Whether to actually remove the outliers
            - Set to False for a dry run that shows what would be removed without actually removing anything

        This command uses the Interquartile Range (IQR) method to detect outliers:
        - Calculates Q1 (25th percentile) and Q3 (75th percentile)
        - Any value outside [Q1 - multiplier*IQR, Q3 + multiplier*IQR] is considered an outlier

        **Examples:**
        `[p]autoremoutliers member` - Automatically remove member count outliers
        `[p]autoremoutliers bank 2.0` - Remove bank outliers with higher tolerance
        `[p]autoremoutliers member 1.0 false` - Show outliers that would be removed without actually removing them
        """
        if multiplier <= 0:
            return await ctx.send("Multiplier must be a positive number.")

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

        # Extract values for statistical analysis
        values = [point[1] for point in data if point[1] is not None]
        if not values:
            return await ctx.send("No valid data points found.")

        # Calculate quartiles and IQR
        values.sort()
        mid = len(values) // 2
        q1_idx = mid // 2
        q3_idx = mid + (len(values) - mid) // 2

        q1 = values[q1_idx]
        q3 = values[q3_idx]
        iqr = q3 - q1

        # Calculate bounds
        lower_bound = q1 - (multiplier * iqr)
        upper_bound = q3 + (multiplier * iqr)

        # Filter out outliers
        original_count = len(data)
        newrows = [i for i in data if i[1] and lower_bound <= i[1] <= upper_bound]
        deleted = original_count - len(newrows)

        if not deleted:
            return await ctx.send("No outliers detected in the data.")

        async with ctx.typing():
            # Only update data if confirm is True
            if confirm:
                if banktype:
                    if is_global:
                        await self.config.data.set(newrows)
                    else:
                        await self.config.guild(ctx.guild).data.set(newrows)
                else:
                    await self.config.guild(ctx.guild).member_data.set(newrows)

            data_type_str = "bank balance" if banktype else "member count"
            stats_msg = (
                f"**Statistical Analysis:**\n"
                f"- First quartile (Q1): {humanize_number(q1)}\n"
                f"- Third quartile (Q3): {humanize_number(q3)}\n"
                f"- Interquartile range (IQR): {humanize_number(iqr)}\n"
                f"- Calculated acceptable range: {humanize_number(lower_bound)} to {humanize_number(upper_bound)}"
            )

            title = "Outlier Detection Results"
            if confirm:
                description = f"Deleted {deleted} outliers from {data_type_str} data."
            else:
                description = f"Dry run: Would delete {deleted} outliers from {data_type_str} data.\nRun the command without `false` to actually remove them."

            embed = discord.Embed(title=title, description=description, color=ctx.author.color)
            embed.add_field(name="Statistics", value=stats_msg, inline=False)

            await ctx.send(embed=embed)
