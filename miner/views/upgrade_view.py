import typing as t

import discord

from ..db.tables import Player


class UpgradeConfirmView(discord.ui.View):
    def __init__(self, player: Player):
        super().__init__(timeout=30)
        self.value: t.Optional[bool] = None
        self.player = player

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False

        return True

    @discord.ui.button(label="Upgrade", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.defer()
        self.stop()
