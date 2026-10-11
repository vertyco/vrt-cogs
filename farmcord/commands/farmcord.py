"""[p]farmcord posts a Play button, and [p]farmcord version shows the version and the credit. /farmcord opens the
game directly. They work in DMs too, since a farm follows its player everywhere"""

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n

from ..abc import MixinMeta
from ..catalog import CREDIT, CREDIT_URL

_ = Translator("FarmCord", __file__)
CREDIT_LINE = f"{CREDIT}: {CREDIT_URL}"


@cog_i18n(_)
class FarmCordCommands(MixinMeta):
    @commands.group(name="farmcord", invoke_without_command=True)
    async def farmcord_group(self, ctx: commands.Context):
        """Post a Play button that opens FarmCord"""
        await ctx.send(_("Press to play:"), view=self.play_view)

    @app_commands.command(name="farmcord", description=_("Open FarmCord"))
    async def farmcord_slash(self, interaction: discord.Interaction):
        hub = self.bot.get_cog("ActivityHub")
        if hub is None:
            await interaction.response.send_message(_("FarmCord needs the ActivityHub cog."), ephemeral=True)
            return
        await hub.launch(interaction, "farmcord")

    @farmcord_group.command(name="version")
    async def farmcord_version(self, ctx: commands.Context):
        """Show FarmCord's version and who designed the game"""
        await ctx.send(
            _("FarmCord is running version {version}.").format(version=self.__version__) + "\n" + CREDIT_LINE
        )
