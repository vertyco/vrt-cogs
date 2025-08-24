import math
from contextlib import suppress
from io import StringIO

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box

from ..common import constants
from ..db.tables import Player


class SearchModal(discord.ui.Modal):
    def __init__(self, current: str):
        super().__init__(title="Search", timeout=240)
        self.query = current
        self.input = discord.ui.TextInput(label="Enter Search Query or Page", default=current)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        self.query = self.input.value
        await interaction.response.defer()
        self.stop()


class Dropdown(discord.ui.Select):
    def __init__(self, callback_func):
        options = [
            discord.SelectOption(label=i.title(), emoji=constants.resource_emoji(i)) for i in constants.RESOURCES
        ]
        super().__init__(placeholder="Change resource type...", options=options)
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.values[0].lower())


class LeaderboardView(discord.ui.View):
    def __init__(self, bot: Red, ctx: commands.Context):
        super().__init__(timeout=240)
        self.bot = bot
        self.author: discord.Member | discord.User = ctx.author
        self.channel: discord.abc.MessageableChannel = ctx.channel

        self.page = 0
        self.page_count = 0
        self.pages: list[discord.Embed] = []
        self.players: list[dict] = []
        self.message: discord.Message | None = None
        self.resource: constants.Resource = "stone"

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def update_players(self):
        players = (
            await Player.select(Player.id, getattr(Player, self.resource))
            .where(getattr(Player, self.resource) > 0)
            .order_by(getattr(Player, self.resource), ascending=False)
        )
        self.players = [p for p in players if self.bot.get_user(p["id"])]

    async def update_pages(self):
        pages: list[discord.Embed] = []
        per_page = 10
        start = 0
        stop = per_page
        max_pages = math.ceil(len(self.players) / per_page)
        color = await self.bot.get_embed_color(self.channel)
        title = f"{constants.resource_emoji(self.resource)} {self.resource.title().rstrip('s')} Leaderboard"

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

            embed = discord.Embed(
                title=title,
                description=f"Top {len(self.players)} miners.\n{box(buffer.getvalue(), lang='py')}",
                color=color,
            )
            footer = f"Page {p + 1}/{max_pages}"
            if position is not None:
                footer += f" | Your Position: {position + 1}"
            embed.set_footer(text=footer)
            pages.append(embed)
            start += per_page
            stop += per_page
        self.page_count = max_pages
        self.pages = pages

    async def change_resource(self, interaction: discord.Interaction, resource: constants.Resource):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.resource = resource
        await self.update_players()
        await self.update_pages()
        await self.refresh(interaction, followup=True)

    async def refresh(self, interaction: discord.Interaction | None = None, followup: bool = False):
        self.clear_items()

        single = [self.close]
        small = [self.left] + single + [self.right]
        large = small + [self.left10, self.right10]
        buttons = large if self.page_count > 10 else small if self.page_count > 1 else single

        self.add_item(Dropdown(self.change_resource))
        for button in buttons:
            self.add_item(button)

        self.page %= len(self.pages)
        if interaction and followup:
            await interaction.edit_original_response(embed=self.pages[self.page], view=self)
        elif interaction:
            await interaction.response.edit_message(embed=self.pages[self.page], view=self)
        elif self.message:
            await self.message.edit(embed=self.pages[self.page], view=self)
        else:
            self.message = await self.channel.send(embed=self.pages[self.page], view=self)

    async def start(self):
        await self.update_players()
        if not self.players:
            return await self.channel.send("No players found.")
        await self.update_pages()
        await self.refresh()

    @discord.ui.button(emoji="\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        await self.refresh(interaction)

    @discord.ui.button(emoji="\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()
        if self.message:
            with suppress(discord.NotFound):
                await self.message.delete()
        self.stop()

    @discord.ui.button(emoji="\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}", style=discord.ButtonStyle.primary)
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        await self.refresh(interaction)

    @discord.ui.button(emoji="\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}", style=discord.ButtonStyle.primary, row=1)
    async def left10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 10
        await self.refresh(interaction)

    @discord.ui.button(emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}", style=discord.ButtonStyle.primary, row=1)
    async def right10(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 10
        await self.refresh(interaction)
