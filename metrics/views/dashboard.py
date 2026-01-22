"""
Interactive Metrics Dashboard - V2 LayoutView Components

This module provides a modern interactive UI for viewing metrics using Discord's
V2 components (LayoutView). Users can select metrics, configure time ranges,
and view multi-metric graphs.
"""

from __future__ import annotations

import asyncio
import logging
import typing as t
from datetime import datetime
from io import BytesIO
from uuid import uuid4

import discord
import pandas as pd
from discord import ui
from redbot.core import commands
from redbot.core.utils.chat_formatting import humanize_number

if t.TYPE_CHECKING:
    from ..main import Metrics

from ..common import plots, utils
from ..db.tables import (
    GlobalEconomySnapshot,
    GlobalMemberSnapshot,
    GlobalPerformanceSnapshot,
    GuildEconomySnapshot,
    GuildMemberSnapshot,
)

log = logging.getLogger("red.vrt.metrics.views.dashboard")


# =============================================================================
# Constants
# =============================================================================

MEMBER_METRICS = {
    "member_total": ("Total Members", "#009DFF"),
    "online_members": ("Online", "#00FF00"),
    "idle_members": ("Idle", "#FFC400"),
    "dnd_members": ("DND", "#FF0000"),
    "offline_members": ("Offline", "#878787"),
}

ECONOMY_METRICS = {
    "bank_total": ("Total Bank", "#FFD700"),
    "average_balance": ("Average Balance", "#C0C0C0"),
}

PERFORMANCE_METRICS = {
    "latency_ms": ("Latency (ms)", "#FF6B6B"),
    "cpu_usage_percent": ("CPU Usage (%)", "#4ECDC4"),
    "memory_usage_percent": ("Memory Usage (%)", "#45B7D1"),
    "memory_used_mb": ("Memory Used (MB)", "#96CEB4"),
    "active_tasks": ("Active Tasks", "#DDA0DD"),
}


# =============================================================================
# Modals
# =============================================================================


class TimeRangeModal(ui.Modal, title="Set Time Range"):
    """Modal for configuring the time range for metrics display."""

    timespan = ui.TextInput(
        label="Time Duration (e.g., 12h, 7d, 30d)",
        placeholder="12h",
        required=False,
        max_length=20,
    )
    start_time = ui.TextInput(
        label="Start Time (optional)",
        placeholder="2024-01-01 00:00",
        required=False,
        max_length=30,
    )
    end_time = ui.TextInput(
        label="End Time (optional)",
        placeholder="2024-01-02 00:00",
        required=False,
        max_length=30,
    )

    def __init__(self, view: "MetricsDashboardLayout"):
        super().__init__()
        self.dashboard_view = view
        # Pre-fill with current values
        if view.timespan:
            self.timespan.default = view.timespan
        if view.start_time:
            self.start_time.default = view.start_time
        if view.end_time:
            self.end_time.default = view.end_time

    async def on_submit(self, interaction: discord.Interaction):
        self.dashboard_view.timespan = self.timespan.value or "12h"
        self.dashboard_view.start_time = self.start_time.value or None
        self.dashboard_view.end_time = self.end_time.value or None
        await self.dashboard_view.refresh(interaction, regenerate_graph=True)


# =============================================================================
# Action Rows
# =============================================================================


class MetricCategoryRow(ui.ActionRow["MetricsDashboardLayout"]):
    """Dropdown for selecting the metric category."""

    def __init__(self, selected_category: str):
        super().__init__()
        self._selected = selected_category
        self._update_options()

    def _update_options(self):
        options = [
            discord.SelectOption(
                label="Member Statistics",
                value="members",
                description="Online, offline, idle, DND member counts",
                emoji="👥",
                default=self._selected == "members",
            ),
            discord.SelectOption(
                label="Economy/Bank",
                value="economy",
                description="Bank totals and average balances",
                emoji="💰",
                default=self._selected == "economy",
            ),
            discord.SelectOption(
                label="Performance",
                value="performance",
                description="Latency, CPU, memory usage",
                emoji="⚡",
                default=self._selected == "performance",
            ),
        ]
        self.category_select.options = options

    @ui.select(placeholder="Select metric category...")
    async def category_select(self, interaction: discord.Interaction, select: ui.Select):
        self.view.selected_category = select.values[0]
        self.view.selected_metrics = []  # Reset selected metrics when category changes
        await self.view.refresh(interaction, regenerate_graph=True)


class MetricSelectRow(ui.ActionRow["MetricsDashboardLayout"]):
    """Multi-select dropdown for choosing specific metrics to display."""

    def __init__(self, category: str, selected_metrics: list[str]):
        super().__init__()
        self._category = category
        self._selected = selected_metrics
        self._update_options()

    def _update_options(self):
        if self._category == "members":
            metric_map = MEMBER_METRICS
        elif self._category == "economy":
            metric_map = ECONOMY_METRICS
        else:
            metric_map = PERFORMANCE_METRICS

        options = []
        for key, (label, _) in metric_map.items():
            options.append(
                discord.SelectOption(
                    label=label,
                    value=key,
                    default=key in self._selected,
                )
            )
        self.metric_select.options = options
        self.metric_select.max_values = len(options)

    @ui.select(placeholder="Select metrics to display...", min_values=1, max_values=5)
    async def metric_select(self, interaction: discord.Interaction, select: ui.Select):
        self.view.selected_metrics = select.values
        await self.view.refresh(interaction, regenerate_graph=True)


class ScopeRow(ui.ActionRow["MetricsDashboardLayout"]):
    """Buttons for selecting global vs guild scope."""

    def __init__(self, show_global: bool, has_guild: bool):
        super().__init__()
        self._show_global = show_global
        self._has_guild = has_guild
        self._update_buttons()

    def _update_buttons(self):
        self.global_button.style = discord.ButtonStyle.primary if self._show_global else discord.ButtonStyle.secondary
        self.guild_button.style = (
            discord.ButtonStyle.primary if not self._show_global else discord.ButtonStyle.secondary
        )
        self.guild_button.disabled = not self._has_guild

    @ui.button(label="Global", emoji="🌐")
    async def global_button(self, interaction: discord.Interaction, button: ui.Button):
        self.view.show_global = True
        await self.view.refresh(interaction, regenerate_graph=True)

    @ui.button(label="This Guild", emoji="🏠")
    async def guild_button(self, interaction: discord.Interaction, button: ui.Button):
        self.view.show_global = False
        await self.view.refresh(interaction, regenerate_graph=True)

    @ui.button(label="⏱️ Time Range", style=discord.ButtonStyle.secondary)
    async def time_range_button(self, interaction: discord.Interaction, button: ui.Button):
        modal = TimeRangeModal(self.view)
        await interaction.response.send_modal(modal)

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.success)
    async def refresh_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.view.refresh(interaction, regenerate_graph=True)


# =============================================================================
# Main Dashboard Layout
# =============================================================================


class MetricsDashboardLayout(ui.LayoutView):
    """Interactive metrics dashboard using V2 LayoutView components."""

    def __init__(
        self,
        ctx: commands.Context,
        cog: "Metrics",
        timeout: float = 300,
        parent: t.Optional[ui.LayoutView] = None,
    ):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.cog = cog
        self.parent = parent
        self.message: t.Optional[discord.Message] = None

        # State
        self.selected_category: str = "members"
        self.selected_metrics: list[str] = ["member_total", "online_members", "offline_members"]
        self.show_global: bool = True
        self.timespan: str = "12h"
        self.start_time: str | None = None
        self.end_time: str | None = None

        # Cached graph data
        self._graph_file: discord.File | None = None
        self._graph_stats: dict | None = None

        self._build_layout()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your dashboard!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        # Disable all components on timeout (following hub.py pattern)
        for child in self.children:
            if hasattr(child, "disabled"):
                setattr(child, "disabled", True)
            elif hasattr(child, "children"):
                for item in getattr(child, "children", []):
                    if hasattr(item, "disabled"):
                        setattr(item, "disabled", True)

    def _build_layout(self):
        """Build the dashboard layout."""
        self.clear_items()

        # Main container
        container = ui.Container(accent_colour=discord.Color.blue())

        # Header
        header_text = f"# 📊 Metrics Dashboard\n-# User: {self.ctx.author.mention}"
        container.add_item(ui.TextDisplay(header_text))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))

        # Current configuration
        scope_text = "🌐 Global" if self.show_global else f"🏠 {self.ctx.guild.name}"
        time_text = f"⏱️ {self.timespan}"
        if self.start_time:
            time_text += f" (from {self.start_time})"
        if self.end_time:
            time_text += f" (to {self.end_time})"

        config_text = f"**Scope:** {scope_text} | **Time:** {time_text}"
        container.add_item(ui.TextDisplay(config_text))

        # Selected metrics display
        if self.selected_metrics:
            if self.selected_category == "members":
                metric_labels = [MEMBER_METRICS.get(m, (m, ""))[0] for m in self.selected_metrics]
            elif self.selected_category == "economy":
                metric_labels = [ECONOMY_METRICS.get(m, (m, ""))[0] for m in self.selected_metrics]
            else:
                metric_labels = [PERFORMANCE_METRICS.get(m, (m, ""))[0] for m in self.selected_metrics]
            metrics_text = f"**Metrics:** {', '.join(metric_labels)}"
            container.add_item(ui.TextDisplay(metrics_text))

        # Stats display if we have them
        if self._graph_stats:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small))
            stats_lines = ["**📈 Statistics:**"]
            for metric_key, stats in self._graph_stats.items():
                if self.selected_category == "members":
                    label = MEMBER_METRICS.get(metric_key, (metric_key, ""))[0]
                elif self.selected_category == "economy":
                    label = ECONOMY_METRICS.get(metric_key, (metric_key, ""))[0]
                else:
                    label = PERFORMANCE_METRICS.get(metric_key, (metric_key, ""))[0]

                stats_lines.append(
                    f"**{label}:** "
                    f"Current: {humanize_number(int(stats['current']))} | "
                    f"Avg: {humanize_number(int(stats['average']))} | "
                    f"Δ: {humanize_number(int(stats['diff']))}"
                )
            container.add_item(ui.TextDisplay("\n".join(stats_lines)))

        # Graph image
        if self._graph_file:
            gallery = ui.MediaGallery()
            gallery.add_item(media=self._graph_file)
            container.add_item(gallery)

        self.add_item(container)

        # Control rows
        has_guild = self.ctx.guild is not None and self.selected_category != "performance"
        self.add_item(MetricCategoryRow(self.selected_category))
        self.add_item(MetricSelectRow(self.selected_category, self.selected_metrics))
        self.add_item(ScopeRow(self.show_global, has_guild))

    async def refresh(self, interaction: discord.Interaction, regenerate_graph: bool = False):
        """Refresh the dashboard view."""
        if regenerate_graph or self._graph_file is None:
            await interaction.response.defer()
            await self._generate_graph()
        self._build_layout()
        files = [self._graph_file] if self._graph_file else []
        await interaction.edit_original_response(view=self, attachments=files)

    async def _generate_graph(self):
        """Generate the metrics graph based on current selections."""
        settings = await self.cog.db_utils.get_create_guild_settings(self.ctx.guild.id)
        global_settings = await self.cog.db_utils.get_create_global_settings()

        # Get appropriate interval for smoothing
        if self.selected_category == "members":
            interval_minutes = global_settings.member_interval
        elif self.selected_category == "economy":
            interval_minutes = global_settings.economy_interval
        else:
            interval_minutes = global_settings.performance_interval

        # Parse time range
        start_time, end_time = utils.get_timespan(
            timespan=self.timespan,
            start_time=self.start_time,
            end_time=self.end_time,
            timezone=settings.timezone,
        )

        # Query data based on category and scope
        data = await self._query_metrics(start_time, end_time)

        if not data or len(data) < 2:
            self._graph_file = None
            self._graph_stats = None
            return

        # Generate graph in thread
        def _prep() -> tuple[discord.File, dict]:
            df = pd.DataFrame.from_records(data)
            df["created_on"] = pd.to_datetime(df["created_on"]).dt.tz_convert(settings.timezone)
            df.set_index("created_on", inplace=True)
            df.index.rename("Date", inplace=True)

            actual_delta = df.index[-1] - df.index[0]
            point_count = len(df.index)
            rolling_window = utils.get_window(actual_delta, point_count, interval_minutes)

            # Calculate stats for each metric
            stats = {}
            for metric_key in self.selected_metrics:
                if metric_key in df.columns:
                    col = df[metric_key].dropna()
                    if len(col) > 0:
                        stats[metric_key] = {
                            "current": col.iloc[-1],
                            "average": col.mean(),
                            "highest": col.max(),
                            "lowest": col.min(),
                            "diff": col.max() - col.min(),
                        }

            # Generate multi-metric plot
            image_bytes = plots.render_multi_metric_plot(
                df,
                self.selected_metrics,
                self._get_metric_map(),
                rolling_window,
            )
            buffer = BytesIO(image_bytes)
            buffer.seek(0)
            file = discord.File(buffer, filename=f"{uuid4()}.png")

            return file, stats

        self._graph_file, self._graph_stats = await asyncio.to_thread(_prep)

    def _get_metric_map(self) -> dict[str, tuple[str, str]]:
        """Get the appropriate metric map for the current category."""
        if self.selected_category == "members":
            return MEMBER_METRICS
        elif self.selected_category == "economy":
            return ECONOMY_METRICS
        else:
            return PERFORMANCE_METRICS

    async def _query_metrics(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> list[dict]:
        """Query metrics data from the database."""
        columns_to_select = ["created_on"] + self.selected_metrics

        if self.selected_category == "members":
            if self.show_global:
                table = GlobalMemberSnapshot
                query = table.select(*[getattr(table, col) for col in columns_to_select])
            else:
                table = GuildMemberSnapshot
                query = table.select(*[getattr(table, col) for col in columns_to_select]).where(
                    table.guild == self.ctx.guild.id
                )
        elif self.selected_category == "economy":
            if self.show_global:
                table = GlobalEconomySnapshot
                query = table.select(*[getattr(table, col) for col in columns_to_select])
            else:
                table = GuildEconomySnapshot
                query = table.select(*[getattr(table, col) for col in columns_to_select]).where(
                    table.guild == self.ctx.guild.id
                )
        else:
            # Performance is global only
            table = GlobalPerformanceSnapshot
            query = table.select(*[getattr(table, col) for col in columns_to_select])

        query = query.where((table.created_on >= start_time) & (table.created_on <= end_time))
        return await query.order_by(table.created_on)


async def open_metrics_dashboard(ctx: commands.Context, cog: "Metrics") -> None:
    """Open the interactive metrics dashboard."""
    view = MetricsDashboardLayout(ctx, cog)
    await view._generate_graph()  # Generate initial graph
    view._build_layout()

    files = [view._graph_file] if view._graph_file else []
    msg = await ctx.send(view=view, files=files)
    view.message = msg
