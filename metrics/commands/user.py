import asyncio
import typing as t
from io import BytesIO
from uuid import uuid4

import discord
import pandas as pd
from redbot.core import bank, commands
from redbot.core.utils.chat_formatting import humanize_number, humanize_timedelta

from ..abc import MixinMeta
from ..common import plots, utils
from ..db.tables import GlobalSnapshot, GuildSnapshot, ensure_db_connection


class User(MixinMeta):
    @commands.hybrid_group(name="metrics")
    @commands.guild_only()
    @ensure_db_connection()
    async def metrics(self, ctx: commands.Context) -> None:
        """View metrics about the bot and server."""

    @metrics.command(name="bank", aliases=["economy"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def bank_metrics(
        self,
        ctx: commands.Context,
        timespan: t.Optional[str] = "12h",
        average_balance: t.Optional[bool] = False,
        show_global: t.Optional[bool] = False,
        start: t.Optional[str] = None,
        end: t.Optional[str] = None,
    ):
        """View bank-related metrics."""
        if await bank.is_global() and not show_global:
            show_global = True

        settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        if not settings.track_bank:
            txt = f"Bank tracking is not enabled for this server. An admin can enable it with `{ctx.clean_prefix}setmetrics track bank`."
            return await ctx.send(txt, ephemeral=True)

        global_settings = await self.db_utils.get_create_global_settings()
        interval_minutes = global_settings.snapshot_interval

        currency_name = await bank.get_currency_name(ctx.guild)
        query_key = "average_balance" if average_balance else "bank_total"

        if show_global:
            title = f"Global Bank Metrics ({currency_name})"
            table = GlobalSnapshot
            query = GlobalSnapshot.select(
                GlobalSnapshot.created_on,
                getattr(GlobalSnapshot, query_key),
            ).where(getattr(GlobalSnapshot, query_key).is_not_null())
        else:
            title = f"Bank Metrics for {ctx.guild.name} ({currency_name})"
            table = GuildSnapshot
            query = GuildSnapshot.select(
                GuildSnapshot.created_on,
                getattr(GuildSnapshot, query_key),
            ).where((GuildSnapshot.guild == ctx.guild.id) & (getattr(GuildSnapshot, query_key).is_not_null()))

        if timespan.lower() == "none":
            timespan = None
        start_time, end_time = utils.get_timespan(
            timespan=timespan,
            start_time=start,
            end_time=end,
            timezone=settings.timezone,
        )
        query = query.where((table.created_on >= start_time) & (table.created_on <= end_time))

        data: list[dict] = await query.order_by(table.created_on)
        if not data:
            return await ctx.send("No data available for the specified timespan.", ephemeral=True)
        if len(data) < 2:
            return await ctx.send("Not enough data points to generate a graph.", ephemeral=True)

        color = await ctx.embed_color()

        def _prep() -> tuple[discord.Embed, discord.File]:
            df = pd.DataFrame.from_records(data)
            # created_on is in UTC, convert to guild timezone
            df["created_on"] = df["created_on"].dt.tz_convert(settings.timezone)
            df.set_index("created_on", inplace=True)
            df.rename(columns={query_key: currency_name}, inplace=True)
            df.index.rename("Date", inplace=True)
            # ------- DATA SMOOTHING -------
            # Apply a rolling average to smooth out the data
            actual_delta = df.index[-1] - df.index[0]
            point_count = len(df.index)
            rolling_window = utils.get_window(actual_delta, point_count, interval_minutes)
            rolling_column = "(Rolling Avg)"
            df[rolling_column] = df[currency_name].rolling(window=rolling_window, min_periods=1).mean()
            df.reset_index(inplace=True)
            # ------- END DATA SMOOTHING -------
            image_bytes = plots.render_bank_plot(df, currency_name, rolling_column)
            buffer = BytesIO(image_bytes)
            buffer.seek(0)
            file = discord.File(buffer, filename=f"{uuid4()}.png")
            timeframe = humanize_timedelta(timedelta=actual_delta)
            dataset_label = "Average Balance" if average_balance else "Total Balance"
            scope_label = "Global" if show_global else ctx.guild.name
            embed = discord.Embed(
                title=title,
                description=f"{dataset_label} trend for **{scope_label}** over **{timeframe}**\nSmoothing window: {rolling_window} points",
                color=color,
            )
            embed.set_image(url=f"attachment://{file.filename}")
            embed.set_footer(text=f"Timezone: {settings.timezone}")
            field = (
                f"`Current: `{humanize_number(int(df[currency_name].iloc[-1]))}\n"
                f"`Average: `{humanize_number(int(df[currency_name].mean()))}\n"
                f"`Highest: `{humanize_number(int(df[currency_name].max()))}\n"
                f"`Lowest:  `{humanize_number(int(df[currency_name].min()))}"
            )
            embed.add_field(name=f"{dataset_label} Stats", value=field, inline=False)
            return embed, file

        embed, file = await asyncio.to_thread(_prep)
        await ctx.send(embed=embed, file=file)

    @metrics.command(name="members", aliases=["membercount", "population"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def member_metrics(
        self,
        ctx: commands.Context,
        timespan: t.Optional[str] = "12h",
        metric: t.Literal["total", "online", "idle", "dnd", "offline"] = "total",
        show_global: t.Optional[bool] = False,
        start: t.Optional[str] = None,
        end: t.Optional[str] = None,
    ):
        """View member-related metrics."""

        settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        if not settings.track_members:
            txt = f"Member tracking is not enabled for this server. An admin can enable it with `{ctx.clean_prefix}setmetrics track members`."
            await ctx.send(txt, ephemeral=True)
            return

        global_settings = await self.db_utils.get_create_global_settings()
        interval_minutes = global_settings.snapshot_interval

        metric_map: dict[str, tuple[str, str, str]] = {
            "total": ("member_total", "Total Members", "#009DFF"),
            "online": ("online_members", "Online Members", "#00FF00"),
            "idle": ("idle_members", "Idle Members", "#FFC400"),
            "dnd": ("dnd_members", "Do Not Disturb Members", "#FF0000"),
            "offline": ("offline_members", "Offline Members", "#878787"),
        }

        metric_key = metric_map[metric.lower()]

        query_key, dataset_label, rolling_color = metric_key

        if show_global:
            title = "Global Member Metrics"
            table = GlobalSnapshot
            query = GlobalSnapshot.select(
                GlobalSnapshot.created_on,
                getattr(GlobalSnapshot, query_key),
            ).where(getattr(GlobalSnapshot, query_key).is_not_null())
        else:
            title = f"Member Metrics for {ctx.guild.name}"
            table = GuildSnapshot
            query = GuildSnapshot.select(
                GuildSnapshot.created_on,
                getattr(GuildSnapshot, query_key),
            ).where((GuildSnapshot.guild == ctx.guild.id) & (getattr(GuildSnapshot, query_key).is_not_null()))

        if timespan.lower() == "none":
            timespan = None
        start_time, end_time = utils.get_timespan(
            timespan=timespan,
            start_time=start,
            end_time=end,
            timezone=settings.timezone,
        )
        query = query.where((table.created_on >= start_time) & (table.created_on <= end_time))

        data: list[dict] = await query.order_by(table.created_on)
        if not data:
            return await ctx.send("No data available for the specified timespan.", ephemeral=True)
        if len(data) < 2:
            return await ctx.send("Not enough data points to generate a graph.", ephemeral=True)

        color = await ctx.embed_color()

        def _prep() -> tuple[discord.Embed, discord.File]:
            df = pd.DataFrame.from_records(data)
            df["created_on"] = df["created_on"].dt.tz_convert(settings.timezone)
            df.set_index("created_on", inplace=True)
            df.rename(columns={query_key: dataset_label}, inplace=True)
            df.index.rename("Date", inplace=True)
            actual_delta = df.index[-1] - df.index[0]
            point_count = len(df.index)
            rolling_window = utils.get_window(actual_delta, point_count, interval_minutes)
            rolling_column = "(Rolling Avg)"
            df[rolling_column] = df[dataset_label].rolling(window=rolling_window, min_periods=1).mean()
            df.reset_index(inplace=True)
            image_bytes = plots.render_member_plot(df, dataset_label, rolling_column, rolling_color)
            buffer = BytesIO(image_bytes)
            buffer.seek(0)
            file = discord.File(buffer, filename=f"{uuid4()}.png")
            timeframe = humanize_timedelta(timedelta=actual_delta)
            scope_label = "Global" if show_global else ctx.guild.name
            embed = discord.Embed(
                title=title,
                description=(
                    f"{dataset_label} trend for **{scope_label}** over **{timeframe}**\n"
                    f"Smoothing window: {rolling_window} points"
                ),
                color=color,
            )
            embed.set_image(url=f"attachment://{file.filename}")
            embed.set_footer(text=f"Timezone: {settings.timezone}")
            field = (
                f"`Current: `{humanize_number(int(df[dataset_label].iloc[-1]))}\n"
                f"`Average: `{humanize_number(int(df[dataset_label].mean()))}\n"
                f"`Highest: `{humanize_number(int(df[dataset_label].max()))}\n"
                f"`Lowest:  `{humanize_number(int(df[dataset_label].min()))}"
            )
            embed.add_field(name=f"{dataset_label} Stats", value=field, inline=False)
            return embed, file

        embed, file = await asyncio.to_thread(_prep)
        await ctx.send(embed=embed, file=file)

    @metrics.command(name="performance", aliases=["perf"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def performance_metrics(
        self,
        ctx: commands.Context,
        timespan: t.Optional[str] = "12h",
        metric: t.Literal["latency", "cpu", "memory", "tasks", "duration"] = "latency",
        start: t.Optional[str] = None,
        end: t.Optional[str] = None,
    ):
        """View bot performance metrics."""

        global_settings = await self.db_utils.get_create_global_settings()
        if not global_settings.track_performance:
            txt = (
                "Performance tracking is not enabled. "
                f"An admin can enable it with `{ctx.clean_prefix}setmetrics track performance`."
            )
            await ctx.send(txt, ephemeral=True)
            return

        settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
        interval_minutes = global_settings.snapshot_interval

        metric_map: dict[str, tuple[str, str, str, int]] = {
            "latency": ("latency_ms", "Latency (ms)", "ms", 2),
            "cpu": ("cpu_usage_percent", "CPU Usage (%)", "%", 2),
            "memory": ("memory_usage_percent", "Memory Usage (%)", "%", 2),
            "tasks": ("active_tasks", "Active Tasks", "", 0),
            "duration": ("snapshot_duration_seconds", "Snapshot Duration (s)", "s", 2),
        }

        query_key, dataset_label, unit_suffix, decimals = metric_map[metric.lower()]

        query = GlobalSnapshot.select(
            GlobalSnapshot.created_on,
            getattr(GlobalSnapshot, query_key),
        ).where(getattr(GlobalSnapshot, query_key).is_not_null())

        if timespan.lower() == "none":
            timespan = None
        start_time, end_time = utils.get_timespan(
            timespan=timespan,
            start_time=start,
            end_time=end,
            timezone=settings.timezone,
        )
        query = query.where((GlobalSnapshot.created_on >= start_time) & (GlobalSnapshot.created_on <= end_time))

        data: list[dict] = await query.order_by(GlobalSnapshot.created_on)
        if not data:
            return await ctx.send("No data available for the specified timespan.", ephemeral=True)
        if len(data) < 2:
            return await ctx.send("Not enough data points to generate a graph.", ephemeral=True)

        color = await ctx.embed_color()

        def _prep() -> tuple[discord.Embed, discord.File]:
            df = pd.DataFrame.from_records(data)
            df["created_on"] = df["created_on"].dt.tz_convert(settings.timezone)
            df.set_index("created_on", inplace=True)
            df.rename(columns={query_key: dataset_label}, inplace=True)
            df.index.rename("Date", inplace=True)
            actual_delta = df.index[-1] - df.index[0]
            point_count = len(df.index)
            rolling_window = utils.get_window(actual_delta, point_count, interval_minutes)
            rolling_column = "(Rolling Avg)"
            df[rolling_column] = df[dataset_label].rolling(window=rolling_window, min_periods=1).mean()
            df.reset_index(inplace=True)
            image_bytes = plots.render_performance_plot(df, dataset_label, rolling_column)
            buffer = BytesIO(image_bytes)
            buffer.seek(0)
            file = discord.File(buffer, filename=f"{uuid4()}.png")
            timeframe = humanize_timedelta(timedelta=actual_delta)

            def format_value(value: float) -> str:
                if pd.isna(value):
                    return "N/A"
                if decimals == 0:
                    return f"{int(round(value))}{f' {unit_suffix}'.rstrip()}"
                return f"{value:.{decimals}f}{f' {unit_suffix}'.rstrip()}"

            embed = discord.Embed(
                title="Global Performance Metrics",
                description=(f"{dataset_label} trend over **{timeframe}**\nSmoothing window: {rolling_window} points"),
                color=color,
            )
            embed.set_image(url=f"attachment://{file.filename}")
            embed.set_footer(text=f"Timezone: {settings.timezone}")
            field = (
                f"`Current: `{format_value(df[dataset_label].iloc[-1])}\n"
                f"`Average: `{format_value(df[dataset_label].mean())}\n"
                f"`Highest: `{format_value(df[dataset_label].max())}\n"
                f"`Lowest:  `{format_value(df[dataset_label].min())}"
            )
            embed.add_field(name=f"{dataset_label} Stats", value=field, inline=False)
            return embed, file

        embed, file = await asyncio.to_thread(_prep)
        await ctx.send(embed=embed, file=file)
