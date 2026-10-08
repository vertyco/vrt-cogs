import logging

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.discord_api import activities_enabled, launch_activity

log = logging.getLogger("red.vrt.activityhub.commands")
_ = Translator("ActivityHub", __file__)


class UserCommands(MixinMeta):
    async def launch(self, interaction: discord.Interaction, key: str | None = None) -> None:
        """
        Open the Activity for whoever ran the command or pressed the button.

        With a game key, the menu opens that game right after login. Game cogs call this.
        """
        # Discord voids the interaction when a launch is refused, so everything is checked first
        if not await activities_enabled(self.bot):
            await interaction.response.send_message(
                _("Activities can't open yet. The bot owner needs to turn them on for this bot."), ephemeral=True
            )
            return
        if key is not None and not await self.launch_allowed(interaction, key):
            return
        try:
            await launch_activity(self.bot, interaction)
        except discord.HTTPException as e:
            log.error("Activity launch failed in %s", interaction.guild_id, exc_info=e)

    async def launch_allowed(self, interaction: discord.Interaction, key: str) -> bool:
        if key not in self.registry.games:
            await interaction.response.send_message(_("That activity isn't installed on this bot."), ephemeral=True)
            return False
        if key in await self.config.disabled():
            await interaction.response.send_message(_("This activity is turned off on this bot."), ephemeral=True)
            return False
        if interaction.guild is not None and key in await self.config.guild(interaction.guild).disabled():
            await interaction.response.send_message(_("This activity is turned off in this server."), ephemeral=True)
            return False
        self.launches.remember(interaction.user.id, key)
        return True

    @app_commands.command(name="activities", description="Open the activities menu")
    @app_commands.guild_only()
    async def activities_slash(self, interaction: discord.Interaction):
        """Open the activities menu"""
        await self.launch(interaction)

    @commands.command(name="activities")
    @commands.guild_only()
    async def activities_text(self, ctx: commands.Context):
        """Post a button that opens the activities menu"""
        await ctx.send(_("Pick a game to play together."), view=self.open_view)
