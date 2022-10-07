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
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from economytrack.abc import MixinMeta

_ = Translator("EconomyTrackCommands", __file__)


@cog_i18n(_)
class EconomyTrackCommands(MixinMeta):
    @commands.group(aliases=["ecotrack"])
    @commands.admin()
    @commands.guild_only()
    async def economytrack(self, ctx: commands.Context):
        """Configure EconomyTrack"""

    @economytrack.command()
    @commands.guildowner()
    @commands.guild_only()
    async def toggle(self, ctx: commands.Context):
        """Enable/Disable economy tracking for this server"""
        async with self.config.guild(ctx.guild).all() as conf:
            if conf["enabled"]:
                conf["enabled"] = False
                await ctx.send(_("Economy tracking has been **Disabled**"))
            else:
                conf["enabled"] = True
                await ctx.send(_("Economy tracking has been **Enabled**"))

    @economytrack.command()
    @commands.is_owner()
    async def maxpoints(self, ctx: commands.Context, max_points: int):
        """
        Set the max amount of data points the bot will store

        **Arguments**
        `<max_points>` Maximum amount of data points to store

        The loop runs every minute, so 1440 points equals 1 day
        The default is 43200 (30 days)
        Set to 0 to store data indefinitely (Not Recommended)
        """
        await self.config.max_points.set(max_points)
        await ctx.tick()

    @economytrack.command()
    async def timezone(self, ctx: commands.Context, timezone: str = None):
        """
        Set your desired timezone for the graph

        **Arguments**
        `<timezone>` A string representing a valid timezone

        Use this command without the argument to get a huge list of valid timezones.
        """
        tzs = pytz.common_timezones
        timezones = "\n".join([t for t in tzs])
        command = f"`{ctx.prefix}ecotrack timezone US/Eastern`"
        text = _(f"Use one of these timezones with this command\n") + _("Example: ") + command
        embeds = []
        if not timezone or timezone not in tzs:
            if not timezone:
                title = _("Valid Timezones")
            else:
                title = _("Invalid Arg, Here are Valid Timezones")
            for p in pagify(timezones, page_length=500):
                em = discord.Embed(
                    title=title,
                    description=f"{text}\n{box(p)}",
                    color=ctx.author.color
                )
                embeds.append(em)

        if embeds:
            for i, em in enumerate(embeds):
                em.set_footer(text=f"Page {i + 1}/{len(embeds)}")
            return await menu(ctx, embeds, DEFAULT_CONTROLS)

        await self.config.guild(ctx.guild).timezone.set(timezone)
        await ctx.tick()

    @economytrack.command()
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
        desc = _(f"`Enabled:    `{enabled}\n"
                 f"`Timezone:   `{timezone}\n"
                 f"`Max Points: `{humanize_number(max_points)} ({mptime})\n"
                 f"`Collected:  `{humanize_number(points)} ({ptime if ptime else 'None'})\n"
                 f"`Timezone:   `{timezone}\n"
                 f"`LoopTime:   `{avg_iter}ms")
        embed = discord.Embed(
            title=_("EconomyTrack Settings"),
            description=desc,
            color=ctx.author.color
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guildowner()
    @commands.guild_only()
    async def remoutliers(self, ctx: commands.Context, max_value: int):
        """Cleanup data above a certain total economy balance"""
        is_global = await bank.is_global()
        if is_global:
            data = await self.config.data()
        else:
            data = await self.config.guild(ctx.guild).data()
        if len(data) < 10:
            embed = discord.Embed(
                description=_("There is not enough data collected. Try again later."),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        newrows = [i for i in data if i[1] <= max_value]
        deleted = len(data) - len(newrows)
        if not deleted:
            return await ctx.send(_("No data to delete"))
        async with ctx.typing():
            if is_global:
                await self.config.data.set(newrows)
            else:
                await self.config.guild(ctx.guild).data.set(newrows)
            await ctx.send(_("Deleted all data points above ") + str(max_value))

    @commands.command(aliases=["bgraph"])
    @commands.cooldown(5, 60.0, BucketType.user)
    @commands.guild_only()
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
                description=_("There is not enough data collected to generate a graph right now. Try again later."),
                color=discord.Color.red()
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
                description=_("There is not enough data collected to generate a graph right now. Try again later."),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        if timespan.lower() == "all":
            alltime = humanize_timedelta(seconds=len(data) * 60)
            title = f"Total economy balance for all time ({alltime})"
        else:
            delta: datetime.timedelta = df.index[-1] - df.index[0]
            title = f"Total economy balance over the last {humanize_timedelta(timedelta=delta)}"

        lowest = df.min().total
        highest = df.max().total
        avg = df.mean().total
        current = df.values[-1][0]
        # current = await self.get_total_bal(ctx.guild)

        desc = f"`DataPoints: `{humanize_number(len(df.values))}\n" \
               f"`BankName:   `{bank_name}\n" \
               f"`Currency:   `{currency_name}"

        field = f"`Current: `{humanize_number(current)}\n" \
                f"`Average: `{humanize_number(round(avg))}\n" \
                f"`Highest: `{humanize_number(highest)}\n" \
                f"`Lowest:  `{humanize_number(lowest)}\n" \
                f"`Diff:    `{humanize_number(highest - lowest)}"

        first = df.values[0][0]
        diff = '+' if current > first else '-'
        field2 = f"{diff} {humanize_number(abs(current - first))}"

        embed = discord.Embed(
            title=title,
            description=desc,
            color=ctx.author.color
        )
        embed.add_field(name=_("Statistics"), value=field)
        embed.add_field(name=_("Change"), value=f"Since <t:{int(df.index[0].timestamp())}:D>\n{box(field2, 'diff')}")

        embed.set_image(url="attachment://plot.png")
        embed.set_footer(text=_(f"Timezone: {timezone}"))
        async with ctx.typing():
            file = await self.get_plot(df)
        await ctx.send(embed=embed, file=file)
