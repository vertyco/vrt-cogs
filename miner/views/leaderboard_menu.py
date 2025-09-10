import math
import typing as t
from contextlib import suppress
from datetime import timedelta
from io import StringIO

import discord
from discord import ui
from piccolo.columns.defaults.timestamptz import TimestamptzNow
from piccolo.query import OrderByRaw
from piccolo.query.functions.aggregate import Sum
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

from ..common import constants
from ..db.tables import ResourceLedger


class ResourceDropdown(ui.ActionRow["LeaderboardView"]):
    options = [discord.SelectOption(label=i.title(), emoji=constants.resource_emoji(i)) for i in constants.RESOURCES]

    def __init__(self, view: "LeaderboardView"):
        self.__view = view
        super().__init__()

    @ui.select(placeholder="Resource", options=options)
    async def select_resource(self, interaction: discord.Interaction, select: ui.Select) -> None:
        with suppress(discord.NotFound):
            await interaction.response.defer()
        choice: constants.Resource = select.values[0].lower()
        self.__view.resource = choice
        await self.__view.update_containers()
        await self.__view.refresh(interaction, followup=True)


class LeaderBoardDeltaDropdown(ui.ActionRow["LeaderboardView"]):
    options = [
        discord.SelectOption(label="Hourly", description="Past 1 hour"),
        discord.SelectOption(label="Daily", description="Past 24 hours"),
        discord.SelectOption(label="Weekly", description="Past 7 days"),
        discord.SelectOption(label="Monthly", description="Past 30 days"),
        discord.SelectOption(label="All Time", description="All time"),
    ]

    def __init__(self, view: "LeaderboardView"):
        self.__view = view
        super().__init__()

    @ui.select(placeholder="Timeframe", options=options)
    async def select_delta(self, interaction: discord.Interaction, select: ui.Select) -> None:
        with suppress(discord.NotFound):
            await interaction.response.defer()
        choice: t.Literal["hourly", "daily", "weekly", "monthly", "all time"] = select.values[0].lower()
        self.__view.lb_type = choice
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

    def __init__(self, bot: Red, ctx: commands.Context, local: bool):
        super().__init__()
        self.bot = bot
        self.author: discord.Member | discord.User = ctx.author
        self.channel: discord.abc.MessageableChannel = ctx.channel
        self.local = local

        self.page = 0
        self.page_count = 0
        self.pages: list[ui.Container] = []
        self.message: discord.Message | None = None

        self.data: list[dict] = []
        self.resource: constants.Resource = "stone"
        self.lb_type: t.Literal["hourly", "daily", "weekly", "monthly", "all time"] = "all time"

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

    async def update_leaderboard_data(self):
        if self.lb_type == "hourly":
            delta = timedelta(hours=1)
        elif self.lb_type == "daily":
            delta = timedelta(days=1)
        elif self.lb_type == "weekly":
            delta = timedelta(weeks=1)
        elif self.lb_type == "monthly":
            delta = timedelta(days=30)
        else:
            delta = None

        query = ResourceLedger.select(ResourceLedger.player, Sum(ResourceLedger.amount).as_alias("total")).where(
            (ResourceLedger.resource == self.resource) & (ResourceLedger.amount > 0)
        )
        if delta:
            query = query.where(ResourceLedger.created_on >= TimestamptzNow().python() - delta)
        query = query.group_by(ResourceLedger.player).order_by(OrderByRaw("total"), ascending=False)

        data: list[dict] = await query
        self.data = []

        for entry in data:
            if self.local:
                user = self.channel.guild.get_member(entry["player"])
            else:
                user = self.bot.get_user(entry["player"])
            if not user:
                continue
            entry["name"] = user.name
            self.data.append(entry)

    async def update_containers(self):
        await self.update_leaderboard_data()
        position = next((i for i, p in enumerate(self.data) if p["player"] == self.author.id), None)

        lb_type = "Global " if not self.local else ""
        header = ui.TextDisplay(
            f"{constants.resource_emoji(self.resource)} **{lb_type}{self.lb_type.title()} {self.resource.title().rstrip('s')} Leaderboard**"
        )

        color = await self.bot.get_embed_color(self.channel)
        if not self.data:
            container = ui.Container(accent_color=color)
            container.add_item(header)
            container.add_item(ui.TextDisplay("No players found."))
            container.add_item(ResourceDropdown(self))
            container.add_item(LeaderBoardDeltaDropdown(self))
            container.add_item(PaginationButtons(self))
            self.page_count = 1
            self.pages = [container]
            return

        pages: list[ui.Container] = []
        per_page = 10
        start = 0
        stop = per_page
        max_pages = math.ceil(len(self.data) / per_page)
        for p in range(max_pages):
            stop = min(stop, len(self.data))
            # Get max spacing of number and username so we can pad placement
            max_num_length = 1
            max_name_length = 0
            for i in range(start, stop):
                entry = self.data[i]
                max_name_length = max(max_name_length, len(entry["name"]))
                max_num_length = max(max_num_length, len(str(i + 1)))

            buffer = StringIO()
            for i in range(start, stop):
                entry = self.data[i]
                name = entry["name"]
                amount = entry.get("total", 0) or 0
                num_padding = " " * (max_num_length - len(str(i + 1)))
                name_padding = " " * (max_name_length - len(name))
                buffer.write(f"{i + 1}.{num_padding} {name}{name_padding} {amount}\n")

            # Now we put together the "container"
            container = ui.Container(accent_color=color)
            container.add_item(header)
            # container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large))
            container.add_item(ui.TextDisplay(f"Top {len(self.data)} miners.\n{box(buffer.getvalue(), lang='py')}"))
            container.add_item(ResourceDropdown(self))
            container.add_item(LeaderBoardDeltaDropdown(self))
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
        await self.update_containers()
        await self.refresh()
