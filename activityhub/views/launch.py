import discord
from redbot.core.i18n import Translator

from ..abc import MixinMeta

_ = Translator("ActivityHub", __file__)


class OpenView(discord.ui.View):
    """Persistent button that opens the activities menu, so it works without syncing slash commands"""

    def __init__(self, cog: MixinMeta):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label=_("Open Activities"), style=discord.ButtonStyle.success, custom_id="activityhub:open")
    async def open_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.launch(interaction)
