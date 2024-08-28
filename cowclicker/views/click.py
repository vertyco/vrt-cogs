import random
import re
from contextlib import suppress

import discord
from redbot.core.bot import Red

from ..db.tables import Click

styles = [
    discord.ButtonStyle.secondary,
    discord.ButtonStyle.primary,
    discord.ButtonStyle.success,
    discord.ButtonStyle.danger,
]


class DynamicButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"CowClicker:(?P<clicks>[0-9]+)",
):
    def __init__(self, clicks: int = 0) -> None:
        self.clicks: int = clicks
        super().__init__(
            discord.ui.Button(
                label=str(clicks),
                style=self.style,
                custom_id=f"CowClicker:{clicks}",
                emoji="🐄",
            )
        )

    @property
    def style(self) -> discord.ButtonStyle:
        if self.clicks < 50:
            return discord.ButtonStyle.secondary
        if self.clicks < 100:
            return discord.ButtonStyle.primary
        if self.clicks < 500:
            return discord.ButtonStyle.success
        if self.clicks < 1000:
            return discord.ButtonStyle.danger
        return random.choice(styles)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(int(match["clicks"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        bot: Red = interaction.client
        cog = bot.get_cog("CowClicker")
        if not cog:
            return await interaction.response.send_message(
                "CowClicker cog is not loaded, try again later", ephemeral=True
            )
        if not cog.db:
            return await interaction.response.send_message(
                "Database connection is not active, try again later", ephemeral=True
            )
        self.clicks += 1
        self.item.label = str(self.clicks)
        self.custom_id = f"CowClicker:{self.clicks}"
        self.item.style = self.style
        await interaction.response.edit_message(view=self.view)
        await Click(author_id=interaction.user.id).save()
        # 1 in a 100,000 chance of sending "MOO!"
        if random.randint(1, 100_000) == 1:
            with suppress(Exception):
                await interaction.response.followup.send("MOO!", ephemeral=True)
