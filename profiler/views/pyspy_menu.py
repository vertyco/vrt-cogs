import asyncio
import typing as t
from contextlib import suppress
from io import BytesIO
from uuid import uuid4

import discord
from redbot.core import commands

from ..common.pyspy_profiler import (
    ProfileResult,
    format_profiling_insights,
    generate_profiling_charts,
)


class PySpyMenu(discord.ui.View):
    """Interactive menu for viewing py-spy profiling results."""

    def __init__(self, ctx: commands.Context, result: ProfileResult):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.result = result

        self.message: discord.Message | None = None
        self.pages: t.List[str] = []
        self.page: int = 0

        self.chart: bytes | None = None
        self.show_chart: bool = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You are not allowed to interact with this menu.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            with suppress(discord.NotFound):
                await self.message.edit(view=self)
        self.stop()

    async def start(self):
        # Generate pages
        self.pages = await asyncio.to_thread(format_profiling_insights, self.result)

        # Generate the chart
        if self.result.functions:
            self.chart = await asyncio.to_thread(generate_profiling_charts, self.result)

        # Update button visibility
        if len(self.pages) < 2:
            self.remove_item(self.left)
            self.remove_item(self.right)

        # Build initial attachments
        files = []
        if self.chart and self.show_chart:
            file = discord.File(BytesIO(self.chart), filename=f"profile_chart_{uuid4()}.png")
            files.append(file)

        content = f"{self.pages[self.page]}\n-# Page {self.page + 1}/{len(self.pages)}"
        self.message = await self.ctx.send(content, view=self, files=files)

    async def update(self):
        self.page %= len(self.pages)

        files = []
        if self.chart and self.show_chart:
            file = discord.File(BytesIO(self.chart), filename=f"profile_chart_{uuid4()}.png")
            files.append(file)

        content = f"{self.pages[self.page]}\n-# Page {self.page + 1}/{len(self.pages)}"
        try:
            await self.message.edit(content=content, view=self, attachments=files)
        except discord.NotFound:
            files = []
            if self.chart and self.show_chart:
                file = discord.File(BytesIO(self.chart), filename=f"profile_chart_{uuid4()}.png")
                files.append(file)
            self.message = await self.ctx.send(content, view=self, files=files)

    @discord.ui.button(
        emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page -= 1
        await self.update()

    @discord.ui.button(style=discord.ButtonStyle.danger, emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        await self.message.delete()
        self.stop()

    @discord.ui.button(emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page += 1
        await self.update()

    @discord.ui.button(label="Toggle Chart", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_chart(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.show_chart = not self.show_chart
        button.label = "Show Chart" if not self.show_chart else "Hide Chart"
        await self.update()

    @discord.ui.button(label="Export Raw Data", style=discord.ButtonStyle.success, row=1)
    async def export_raw(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Export the raw speedscope JSON data."""
        if not self.result.raw_data:
            return await interaction.response.send_message("No raw data available.", ephemeral=True)

        with suppress(discord.NotFound):
            await interaction.response.defer()

        import orjson

        raw_bytes = orjson.dumps(self.result.raw_data, option=orjson.OPT_INDENT_2)
        file = discord.File(
            BytesIO(raw_bytes),
            filename=f"profile_{self.result.duration}s.speedscope.json",
        )
        await interaction.followup.send(
            content=(
                "**Raw Profile Data (Speedscope Format)**\n"
                "You can visualize this at https://speedscope.app by dragging and dropping the file.\n"
                "This provides an interactive flamegraph view of the profiling data."
            ),
            file=file,
            ephemeral=True,
        )
