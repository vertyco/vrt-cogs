import math
from contextlib import suppress
from io import StringIO

import discord
from discord import ui
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

from ..common import constants
from ..db.tables import Player


class ResourceDropdown(ui.ActionRow["LeaderboardView"]):
    options = [discord.SelectOption(label=i.title(), emoji=constants.resource_emoji(i)) for i in constants.RESOURCES]

    def __init__(self, view: "LeaderboardView"):
        self.__view = view
        super().__init__()

    @ui.select(placeholder="Change resource type", options=options)
    async def select_resource(self, interaction: discord.Interaction, select: ui.Select) -> None:
        with suppress(discord.NotFound):
            await interaction.response.defer()
        choice: constants.Resource = select.values[0].lower()
        self.__view.resource = choice
        await self.__view.update_players()
        await self.__view.update_containers()
        await self.__view.refresh(interaction, followup=True)


class PaginationButtons(ui.ActionRow["LeaderboardView"]):
    def __init__(self, view: "LeaderboardView"):
        self.__view = view
        if self.__view.page_count > 10:
            self.remove_item(self.left)
            self.remove_item(self.right)
        super().__init__()

    @ui.button(emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.__view.page -= 1
        await self.__view.refresh(interaction)

    @ui.button(emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if self.__view.message:
            with suppress(discord.NotFound):
                await self.__view.message.delete()
        self.__view.stop()

    @ui.button(emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.__view.page += 1
        await self.__view.refresh(interaction)


class LeaderboardView(ui.LayoutView):
    row = ui.ActionRow()

    def __init__(self, bot: Red, ctx: commands.Context):
        super().__init__()
        self.bot = bot
        self.author: discord.Member | discord.User = ctx.author
        self.channel: discord.abc.MessageableChannel = ctx.channel

        self.page = 0
        self.page_count = 0
        self.pages: list[ui.Container] = []
        self.players: list[dict] = []
        self.message: discord.Message | None = None
        self.resource: constants.Resource = "stone"

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            # Disable components
            page: ui.Container = self.pages[self.page]
            for item in page.children:
                if hasattr(item, "disabled"):
                    setattr(item, "disabled", True)
                elif isinstance(item, ui.ActionRow):
                    for child in item.children:
                        if hasattr(child, "disabled"):
                            setattr(child, "disabled", True)
            await self.refresh()
        self.stop()

    async def update_players(self):
        players = (
            await Player.select(Player.id, getattr(Player, self.resource))
            .where(getattr(Player, self.resource) > 0)
            .order_by(getattr(Player, self.resource), ascending=False)
        )
        self.players = [p for p in players if self.bot.get_user(p["id"])]

    async def update_containers(self):
        pages: list[ui.Container] = []
        per_page = 10
        start = 0
        stop = per_page
        max_pages = math.ceil(len(self.players) / per_page)
        color = await self.bot.get_embed_color(self.channel)
        header = ui.TextDisplay(
            f"{constants.resource_emoji(self.resource)} **{self.resource.title().rstrip('s')} Leaderboard**"
        )
        # Find out what position the author is in
        position = next((i for i, p in enumerate(self.players) if p["id"] == self.author.id), None)
        for p in range(max_pages):
            stop = min(stop, len(self.players))

            # Get max spacing of number and username so we can pad placement
            max_num_length = 1
            max_name_length = 0

            for i in range(start, stop):
                player = self.players[i]
                user = self.bot.get_user(player["id"])
                max_name_length = max(max_name_length, len(user.name if user else player["id"]))
                max_num_length = max(max_num_length, len(str(i + 1)))

            buffer = StringIO()
            for i in range(start, stop):
                player = self.players[i]
                user = self.bot.get_user(player["id"])
                name = user.name if user else str(player["id"])
                amount = player.get(self.resource, 0)
                num_padding = " " * (max_num_length - len(str(i + 1)))
                name_padding = " " * (max_name_length - len(name))
                buffer.write(f"{i + 1}.{num_padding} {name}{name_padding} {amount}\n")

            # Now we put together the "container"
            container = ui.Container(accent_color=color)
            container.add_item(header)
            # container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
            container.add_item(ui.TextDisplay(f"Top {len(self.players)} miners.\n{box(buffer.getvalue(), lang='py')}"))
            container.add_item(ResourceDropdown(self))
            # container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
            container.add_item(PaginationButtons(self))
            footer = f"Page {p + 1}/{max_pages}"
            if position is not None:
                footer += f" | Your Position: {position + 1}"
            container.add_item(ui.TextDisplay(f"-# {footer}"))
            pages.append(container)
            start += per_page
            stop += per_page

        self.page_count = max_pages
        self.pages = pages

    async def refresh(self, interaction: discord.Interaction | None = None, followup: bool = False):
        self.page %= len(self.pages)
        self.clear_items()
        self.add_item(self.pages[self.page])
        if interaction and followup:
            await interaction.edit_original_response(view=self)
        elif interaction:
            await interaction.response.edit_message(view=self)
        elif self.message:
            await self.message.edit(view=self)
        else:
            self.message = await self.channel.send(view=self)

    async def start(self):
        await self.update_players()
        if not self.players:
            return await self.channel.send("No players found.")
        await self.update_containers()
        await self.refresh()
