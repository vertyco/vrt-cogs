import logging
import math
import typing as t

import discord
from discord import ui
from redbot.core import commands

log = logging.getLogger("red.vrt.glassrelay.views.product_picker")

PER_PAGE = 25  # the most options Discord allows in one dropdown


def product_option(product_id: int, name: str) -> discord.SelectOption:
    # Discord refuses option labels over 100 characters
    return discord.SelectOption(label=name[:100], value=str(product_id), description=f"Product ID {product_id}")


class ProductPicker(ui.LayoutView):
    """A dropdown of products. Picking one runs on_pick and shows the text it returns."""

    def __init__(
        self,
        ctx: commands.Context,
        heading: str,
        choices: list[discord.SelectOption],
        on_pick: t.Callable[[int], t.Awaitable[str]],
    ):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.heading = heading
        self.choices = choices
        self.on_pick = on_pick
        self.page = 0
        self.message: discord.Message | None = None
        self.select = ui.Select(placeholder="Pick a product")
        self.select.callback = self.picked
        self.build()

    def page_count(self) -> int:
        return math.ceil(len(self.choices) / PER_PAGE)

    def build(self) -> None:
        self.clear_items()
        self.select.options = self.choices[self.page * PER_PAGE : (self.page + 1) * PER_PAGE]
        container = ui.Container(ui.TextDisplay(f"### {self.heading}"), ui.ActionRow(self.select))
        if self.page_count() > 1:
            previous = ui.Button(label="Previous", disabled=self.page == 0)
            previous.callback = self.previous
            following = ui.Button(label="Next", disabled=self.page == self.page_count() - 1)
            following.callback = self.next
            container.add_item(ui.ActionRow(previous, following))
            container.add_item(ui.TextDisplay(f"-# Page {self.page + 1} of {self.page_count()}"))
        self.add_item(container)

    def show(self, text: str) -> None:
        """Swap the dropdown for a line of text"""
        self.clear_items()
        self.add_item(ui.Container(ui.TextDisplay(f"### {self.heading}\n{text}")))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        self.show("This menu timed out. Run the command again.")
        try:
            await self.message.edit(view=self)
        except discord.HTTPException as e:
            log.warning("Couldn't edit the timed out product menu", exc_info=e)

    async def previous(self, interaction: discord.Interaction) -> None:
        self.page -= 1
        self.build()
        await interaction.response.edit_message(view=self)

    async def next(self, interaction: discord.Interaction) -> None:
        self.page += 1
        self.build()
        await interaction.response.edit_message(view=self)

    async def picked(self, interaction: discord.Interaction) -> None:
        self.stop()
        product_id = int(self.select.values[0])
        self.show("Working on it...")
        await interaction.response.edit_message(view=self)
        try:
            text = await self.on_pick(product_id)
        except Exception as e:
            log.error(f"Product menu action failed in {self.ctx.guild}", exc_info=e)
            text = "Something went wrong. The bot owner can find the error in the bot's logs."
        self.show(text)
        await interaction.edit_original_response(view=self)
