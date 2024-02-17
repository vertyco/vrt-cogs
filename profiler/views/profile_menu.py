import asyncio
import typing as t
from contextlib import suppress

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import text_to_file

from ..common.formatting import (
    format_method_pages,
    format_method_tables,
    format_runtime_pages,
)
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
        super().__init__(timeout=None)
        self.ctx = ctx
        self.db = db

        self.message: discord.Message = None
        self.pages: t.List[str] = []
        self.page: int = 0

        self.tables: t.List[str] = []

        self.sorting_by: str = "Avg"
        self.query: t.Union[str, None] = None

        self.inspecting: bool = False
        self.skip10_removed: bool = False
        self.remove_item(self.back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You are not allowed to interact with this menu", ephemeral=True)
            return False
        return True

    async def start(self):
        self.pages = await asyncio.to_thread(format_runtime_pages, self.db.stats, "Avg")
        if len(self.pages) < 20:
            self.remove_item(self.right10)
            self.remove_item(self.left10)
            self.skip10_removed = True

        self.message = await self.ctx.send(self.pages[self.page], view=self)

    async def update(self):
        if len(self.pages) > 20 and self.skip10_removed:
            self.add_item(self.right10)
            self.add_item(self.left10)
            self.skip10_removed = False
        elif len(self.pages) <= 20 and not self.skip10_removed:
            self.remove_item(self.right10)
            self.remove_item(self.left10)
            self.skip10_removed = True
        self.page %= len(self.pages)

        if self.inspecting and self.tables:
            file = text_to_file(self.tables[self.page], filename="profile.txt")
            await self.message.edit(content=self.pages[self.page], view=self, attachments=[file])
        else:
            await self.message.edit(content=self.pages[self.page], view=self, attachments=[])

    @discord.ui.button(emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}", style=discord.ButtonStyle.primary)
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

    @discord.ui.button(
        emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}",
        style=discord.ButtonStyle.primary,
    )
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.page += 1
        await self.update()

    @discord.ui.button(emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}", style=discord.ButtonStyle.primary)
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()

    @discord.ui.button(label="Filter", style=discord.ButtonStyle.secondary, row=1)
    async def filter_results(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SearchModal(self.query, "Filter Results", "Enter Search Query")
        await interaction.response.send_modal(modal)
        await modal.wait()
        if modal.query is None:
            return

        self.query = modal.query
        self.pages = await asyncio.to_thread(format_runtime_pages, self.db.stats, self.sorting_by, self.query)
        await self.update()

    @discord.ui.button(label="Inspect Method", style=discord.ButtonStyle.secondary, row=1)
    async def inspect(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.db.verbose:
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
            return await interaction.response.send_message("No method found with that key")

        self.inspecting = True
        self.pages = await asyncio.to_thread(format_method_pages, modal.query, method_stats)
        self.tables = await asyncio.to_thread(format_method_tables, method_stats)
        self.add_item(self.back)
        self.remove_item(self.filter_results)
        self.remove_item(self.change_sorting)
        self.remove_item(self.inspect)
        await self.update()

    @discord.ui.button(label="Sort: Avg", style=discord.ButtonStyle.success, row=2)
    async def change_sorting(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            self.sorting_by = "LHC"
            button.label = "Sort: Last Hour Calls"
        elif self.sorting_by == "LHC":
            self.sorting_by = "Name"
            button.label = "Sort: Name"

        self.pages = await asyncio.to_thread(format_runtime_pages, self.db.stats, self.sorting_by, self.query)
        await self.update()

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=3)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if not self.inspecting:
            return
        self.add_item(self.filter_results)
        self.add_item(self.change_sorting)
        self.add_item(self.inspect)
        self.remove_item(self.back)
        self.inspecting = False
        self.tables.clear()
        self.pages = await asyncio.to_thread(format_runtime_pages, self.db.stats, self.sorting_by, self.query)
        await self.update()
