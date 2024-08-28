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
    template=r"counter:(?P<count>[0-9]+):messageid:(?P<id>[0-9]+)",
):
    def __init__(self, messageid: int, count: int = 0) -> None:
        self.messageid: int = messageid
        self.count: int = count
        super().__init__(
            discord.ui.Button(
                label=str(count),
                style=self.style,
                custom_id=f"counter:{count}:messageid:{messageid}",
                emoji="🐄",
            )
        )

    @property
    def style(self) -> discord.ButtonStyle:
        if self.count < 50:
            return discord.ButtonStyle.secondary
        if self.count < 100:
            return discord.ButtonStyle.primary
        if self.count < 500:
            return discord.ButtonStyle.success
        if self.count < 1000:
            return discord.ButtonStyle.danger
        return random.choice(styles)

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        count = int(match["count"])
        messageid = int(match["id"])
        return cls(messageid, count=count)

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
        self.count += 1
        self.item.label = str(self.count)
        self.custom_id = f"counter:{self.count}:messageid:{self.messageid}"
        self.item.style = self.style
        await interaction.response.edit_message(view=self.view)
        await Click(author_id=interaction.user.id).save()
        # 1 in a 100,000 chance of sending "MOO!"
        if random.randint(1, 100_000) == 1:
            with suppress(Exception):
                await interaction.response.followup.send("MOO!", ephemeral=True)
