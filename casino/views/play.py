import discord
from redbot.core.i18n import Translator

_ = Translator("Casino", __file__)


class PlayView(discord.ui.View):
    """A Play button that opens the casino, and keeps working after 3 minutes and after the bot restarts"""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label=_("Play"), style=discord.ButtonStyle.success, custom_id="casino:play")
    async def play(self, interaction: discord.Interaction, button: discord.ui.Button):
        hub = self.cog.bot.get_cog("ActivityHub")
        if hub is None:
            await interaction.response.send_message(_("The casino needs the ActivityHub cog."), ephemeral=True)
            return
        # launch must be the first reply to the interaction, and handles its own problems
        await hub.launch(interaction, "casino")
