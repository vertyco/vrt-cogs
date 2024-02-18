import asyncio
import typing as t
from contextlib import suppress
from io import BytesIO

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import text_to_file

from ..common.formatting import (
    format_method_pages,
    format_method_tables,
    format_runtime_pages,
)
from ..common.generator import generate_line_graph
from ..common.models import DB


class SearchModal(discord.ui.Modal):
    def __init__(self, current: t.Union[str, None], title: str, label: str):
        super().__init__(title=title, timeout=240)
        self.query = current
        self.input = discord.ui.TextInput(
            label=label,
            style=discord.TextStyle.short,
            required=False,
            default=current,
            max_length=50,
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.query = self.input.value
        await interaction.response.defer()
        self.stop()


class ProfileMenu(discord.ui.View):
    def __init__(self, ctx: commands.Context, db: DB):
        super().__init__(timeout=1800)
        self.ctx = ctx
        self.db = db

        self.message: discord.Message = None
        self.pages: t.List[str] = []
        self.page: int = 0

        self.tables: t.List[str] = []
        self.plot: bytes = None

        self.sorting_by: str = "Avg"
        self.query: t.Union[str, None] = None

        self.inspecting: bool = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You are not allowed to interact with this menu", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            self.left10.disabled = True
            self.left.disabled = True
            self.close.disabled = True
            self.right.disabled = True
            self.right10.disabled = True
            self.filter_results.disabled = True
            self.inspect.disabled = True
            self.change_sorting.disabled = True
            self.back.disabled = True
            self.refresh.disabled = True
            with suppress(discord.NotFound):
                await self.message.edit(view=self)

        self.stop()

    async def start(self):
        self.remove_item(self.back)

        self.pages = await asyncio.to_thread(format_runtime_pages, self.db, "Avg")
        if len(self.pages) < 15:
            self.remove_item(self.right10)
            self.remove_item(self.left10)

        self.message = await self.ctx.send(self.pages[self.page], view=self)

    async def update(self):
        self.clear_items()
        if self.inspecting:
            self.add_item(self.left)
            self.add_item(self.close)
            self.add_item(self.right)
            if len(self.pages) >= 15:
                self.add_item(self.left10)
            self.add_item(self.back)
            if len(self.pages) >= 15:
                self.add_item(self.right10)
        else:
            self.add_item(self.left)
            self.add_item(self.close)
            self.add_item(self.right)
            self.add_item(self.filter_results)
            self.add_item(self.inspect)
            self.add_item(self.change_sorting)
            self.add_item(self.refresh)
            if len(self.pages) >= 15:
                self.add_item(self.left10)
                self.add_item(self.right10)

        self.page %= len(self.pages)

        if self.inspecting and self.tables:
            file = text_to_file(self.tables[self.page], filename="profile.txt")
            files = [file]
            if self.plot:
                file = discord.File(BytesIO(self.plot), filename="plot.png")
                files.append(file)
            try:
                await self.message.edit(content=self.pages[self.page], view=self, attachments=files)
            except discord.NotFound:
                self.message = await self.ctx.send(self.pages[self.page], view=self, files=files)
        else:
            self.plot = None
            try:
                await self.message.edit(content=self.pages[self.page], view=self, attachments=[])
            except discord.NotFound:
                self.message = await self.ctx.send(self.pages[self.page], view=self)

    @discord.ui.button(emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}", style=discord.ButtonStyle.primary, row=4)
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page -= 10
        await self.update()

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
    async def close(self, interaction: discord.Interaction, button: discord.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        await self.message.delete()

    @discord.ui.button(emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page += 1
        await self.update()

    @discord.ui.button(emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}", style=discord.ButtonStyle.primary, row=4)
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page += 10
        await self.update()

    @discord.ui.button(label="Filter", style=discord.ButtonStyle.secondary, row=1)
    async def filter_results(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchModal(self.query, "Filter Results", "Enter Search Query")
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.query is None:
            return

        self.query = modal.query
        self.pages = await asyncio.to_thread(format_runtime_pages, self.db, self.sorting_by, self.query)
        await self.update()

    @discord.ui.button(label="Inspect Method", style=discord.ButtonStyle.secondary, row=1)
    async def inspect(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.db.verbose and not self.db.verbose_methods:
            return await interaction.response.send_message("Verbose stats are not enabled", ephemeral=True)

        modal = SearchModal(None, "Inpsect a Method", "Enter Method Key")
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.query is None:
            return

        for methodlist in self.db.stats.values():
            if method_stats := methodlist.get(modal.query):
                break
        else:
            return await interaction.followup.send("No method found with that key", ephemeral=True)

        if not self.db.verbose:
            if not any(i.func_profiles for i in method_stats):
                return await interaction.followup.send("This method isn't being profiled verbosely", ephemeral=True)

        self.inspecting = True
        self.pages = await asyncio.to_thread(format_method_pages, modal.query, method_stats)
        self.tables = await asyncio.to_thread(format_method_tables, method_stats)
        if len(method_stats) > 10:
            self.plot = await asyncio.to_thread(generate_line_graph, method_stats)
        await self.update()

    @discord.ui.button(label="Sort: Avg", style=discord.ButtonStyle.success, row=2)
    async def change_sorting(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()

        if self.sorting_by == "Name":
            self.sorting_by = "Max"
            button.label = "Sort: Max"
        elif self.sorting_by == "Max":
            self.sorting_by = "Min"
            button.label = "Sort: Min"
        elif self.sorting_by == "Min":
            self.sorting_by = "Avg"
            button.label = "Sort: Avg"
        elif self.sorting_by == "Avg":
            self.sorting_by = "CPM"
            button.label = "Sort: CPM"
        elif self.sorting_by == "CPM":
            self.sorting_by = "Count"
            button.label = f"Sort: Last {'Hour' if self.db.delta == 1 else f'{self.db.delta}hrs'}"
        elif self.sorting_by == "Count":
            self.sorting_by = "Impact"
            button.label = "Sort: Impact Score"
        elif self.sorting_by == "Impact":
            self.sorting_by = "Name"
            button.label = "Sort: Name"

        self.pages = await asyncio.to_thread(format_runtime_pages, self.db, self.sorting_by, self.query)
        await self.update()

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.success, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()

        self.pages = await asyncio.to_thread(format_runtime_pages, self.db, self.sorting_by, self.query)
        await self.update()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=4)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()

        if not self.inspecting:
            return
        self.inspecting = False
        self.tables.clear()
        self.pages = await asyncio.to_thread(format_runtime_pages, self.db, self.sorting_by, self.query)
        await self.update()
