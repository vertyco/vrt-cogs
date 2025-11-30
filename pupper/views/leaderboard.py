import math
from contextlib import suppress
from io import StringIO

import discord
from discord import ui
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

DOG_EMOJI = "\N{DOG FACE}"
PAW_EMOJI = "\N{PAW PRINTS}"


class PaginationButtons(ui.ActionRow["PupperLeaderboard"]):
    def __init__(self, view: "PupperLeaderboard"):
        self.__view = view
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


class PupperLeaderboard(ui.LayoutView):
    def __init__(self, bot: Red, ctx: commands.Context, config, local: bool = True):
        super().__init__()
        self.bot = bot
        self.config = config
        self.author: discord.Member | discord.User = ctx.author
        self.guild: discord.Guild = ctx.guild
        self.channel: discord.abc.MessageableChannel = ctx.channel
        self.local = local

        self.page = 0
        self.page_count = 0
        self.pages: list[ui.Container] = []
        self.message: discord.Message | None = None

        self.data: list[dict] = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            # Disable components
            for page in self.pages:
                for item in page.children:
                    if hasattr(item, "disabled"):
                        setattr(item, "disabled", True)
                    elif isinstance(item, ui.ActionRow):
                        for child in item.children:
                            if hasattr(child, "disabled"):
                                setattr(child, "disabled", True)
            await self.refresh()
        self.stop()

    async def fetch_leaderboard_data(self) -> None:
        """Fetch and sort pet counts for the leaderboard."""
        self.data = []

        if self.local:
            # Guild-only leaderboard
            all_members = await self.config.all_members(self.guild)
            for user_id, user_data in all_members.items():
                pets = user_data.get("pets", 0)
                if pets <= 0:
                    continue
                user = self.guild.get_member(user_id)
                if not user:
                    continue
                self.data.append({"user_id": user_id, "name": user.display_name, "pets": pets})
        else:
            # Global leaderboard (all guilds)
            all_data = await self.config.all_members()
            # Aggregate across guilds
            user_totals: dict[int, int] = {}
            for guild_id, members in all_data.items():
                for user_id, user_data in members.items():
                    pets = user_data.get("pets", 0)
                    if pets <= 0:
                        continue
                    user_totals[user_id] = user_totals.get(user_id, 0) + pets

            for user_id, total_pets in user_totals.items():
                user = self.bot.get_user(user_id)
                if not user:
                    continue
                self.data.append({"user_id": user_id, "name": user.name, "pets": total_pets})

        # Sort by pet count descending
        self.data.sort(key=lambda x: x["pets"], reverse=True)

    async def build_pages(self) -> None:
        """Build the container pages for the leaderboard."""
        await self.fetch_leaderboard_data()

        # Find the author's position
        position = next((i for i, p in enumerate(self.data) if p["user_id"] == self.author.id), None)

        lb_type = "Global" if not self.local else "Server"
        header = ui.TextDisplay(f"{DOG_EMOJI} **{lb_type} Petting Leaderboard** {PAW_EMOJI}")

        color = await self.bot.get_embed_color(self.channel)

        if not self.data:
            container = ui.Container(accent_color=color)
            container.add_item(header)
            container.add_item(ui.TextDisplay("No one has pet the doggo yet! Be the first! 🐕"))
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

            # Calculate padding for alignment
            max_num_length = len(str(stop))
            max_name_length = max(len(entry["name"]) for entry in self.data[start:stop])

            buffer = StringIO()
            for i in range(start, stop):
                entry = self.data[i]
                name = entry["name"]
                pets = entry["pets"]
                num_padding = " " * (max_num_length - len(str(i + 1)))
                name_padding = " " * (max_name_length - len(name))
                buffer.write(f"{i + 1}.{num_padding} {name}{name_padding} {pets} pets\n")

            container = ui.Container(accent_color=color)
            container.add_item(header)
            container.add_item(
                ui.TextDisplay(f"Top {len(self.data)} pet enthusiasts:\n{box(buffer.getvalue(), lang='py')}")
            )
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

    async def refresh(self, interaction: discord.Interaction | None = None) -> None:
        """Refresh the view with the current page."""
        self.page %= len(self.pages)
        self.clear_items()
        self.add_item(self.pages[self.page])

        if interaction:
            with suppress(discord.NotFound):
                await interaction.response.edit_message(view=self)
        elif self.message:
            with suppress(discord.NotFound):
                await self.message.edit(view=self)
        else:
            self.message = await self.channel.send(view=self)

    async def start(self) -> None:
        """Initialize and display the leaderboard."""
        await self.build_pages()
        await self.refresh()
