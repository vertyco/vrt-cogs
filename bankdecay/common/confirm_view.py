from contextlib import suppress

import discord
from redbot.core.i18n import Translator

_ = Translator("BankDecay", __file__)


class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=60)
        self.author = author
        self.yes.label = _("Yes")
        self.no.label = _("No")

        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False

        return True

    async def on_timeout(self) -> None:
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()

        self.value = True
        self.stop()

    @discord.ui.button(style=discord.ButtonStyle.primary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        with suppress(discord.NotFound):
            await interaction.response.defer()

        self.value = False
        self.stop()
