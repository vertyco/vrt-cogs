import random
from contextlib import suppress

import discord

from ..abc import MixinMeta
from ..db.tables import Click

colors = [
    discord.ButtonStyle.primary,
    discord.ButtonStyle.secondary,
    discord.ButtonStyle.success,
    discord.ButtonStyle.danger,
]


class ClickView(discord.ui.View):
    def __init__(self, cog: MixinMeta, custom_id: str):
        super().__init__(timeout=None)
        self.cog = cog

        self.click.custom_id = custom_id

    @discord.ui.button(label="0", emoji="🐄")
    async def click(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.label = str(int(button.label) + 1)
        button.style = random.choice(colors)
        await interaction.response.edit_message(view=self)
        await Click(author_id=interaction.user.id).save()
        # 1 in a 100,000 chance of sending "MOO!"
        if random.randint(1, 100_000) == 1:
            with suppress(Exception):
                await interaction.response.followup.send("MOO!", ephemeral=True)
