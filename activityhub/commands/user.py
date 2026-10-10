import logging

import discord
from discord import app_commands
from discord.ext import commands as dpy_commands
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.discord_api import activities_enabled, launch_activity
from ..views.launch import add_button, editable_view, has_button, launch_view, remove_button

log = logging.getLogger("red.vrt.activityhub.commands")
_ = Translator("ActivityHub", __file__)


class UserCommands(MixinMeta):
    async def launch(self, interaction: discord.Interaction | dpy_commands.Context, key: str | None = None) -> bool:
        """
        Open the Activity for whoever ran the command or pressed the button.

        With a game key, the menu opens that game right after login. Game cogs call this.
        Takes the discord.Interaction, or a hybrid command's ctx when it ran as a slash command.
        Returns True when the Activity opened, and False when it was refused or Discord failed.
        """
        if isinstance(interaction, dpy_commands.Context):
            if interaction.interaction is None:
                raise TypeError(
                    "hub.launch() needs the discord.Interaction from a button press or slash command. "
                    "A text command has none: post a button that calls launch instead (DEVELOPERS.md section 13)."
                )
            interaction = interaction.interaction
        # Opening the Activity is a reply to the interaction, and an interaction gets only one first reply
        if interaction.response.is_done():
            raise RuntimeError(
                "hub.launch() must be the first reply to this interaction. "
                "Remove the defer() or send_message() before it."
            )
        # Discord voids the interaction when a launch is refused, so everything is checked first
        if not await activities_enabled(self.bot):
            await interaction.response.send_message(
                _("Activities can't open yet. The bot owner needs to turn them on for this bot."), ephemeral=True
            )
            return False
        if key is not None and not await self.launch_allowed(interaction, key):
            return False
        try:
            await launch_activity(self.bot, interaction)
        except discord.HTTPException as e:
            log.error("Activity launch failed in %s", interaction.guild_id, exc_info=e)
            if key is not None:
                # Otherwise the game would open by itself the next time this player opens the menu
                self.launches.forget_user(interaction.user.id)
            return False
        return True

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

    @commands.group(name="activities", invoke_without_command=True)
    @commands.guild_only()
    async def activities_text(self, ctx: commands.Context):
        """Post a button that opens the activities menu"""
        await ctx.send(_("Pick a game to play together."), view=launch_view())

    @activities_text.command(name="pin")
    @commands.admin_or_permissions(manage_guild=True)
    async def pin_button(self, ctx: commands.Context, message: discord.Message):
        """
        Add the Open Activities button to a message the bot sent

        `message` is a message link, or the message's ID when it is in this channel.
        The message keeps its text, embeds and other buttons.
        """
        if not await self.check_editable(ctx, message):
            return
        view = editable_view(message)
        if has_button(view):
            await ctx.send(_("That message already has the button."))
            return
        try:
            add_button(view)
        except ValueError:
            await ctx.send(_("That message has no room for another button."))
            return
        if await self.edit_buttons(ctx, message, view):
            await ctx.send(_("Added the Open Activities button to that message."))

    @activities_text.command(name="unpin")
    @commands.admin_or_permissions(manage_guild=True)
    async def unpin_button(self, ctx: commands.Context, message: discord.Message):
        """
        Take the Open Activities button off a message the bot sent

        `message` is a message link, or the message's ID when it is in this channel.
        """
        if not await self.check_editable(ctx, message):
            return
        view = editable_view(message)
        if not has_button(view):
            await ctx.send(_("That message doesn't have the button."))
            return
        remove_button(view)
        if await self.edit_buttons(ctx, message, view):
            await ctx.send(_("Took the Open Activities button off that message."))

    async def check_editable(self, ctx: commands.Context, message: discord.Message) -> bool:
        if message.author.id != self.bot.user.id:
            await ctx.send(_("I can only change messages I sent."))
            return False
        # A message link can point into any server the bot is in
        if message.guild is None or message.guild.id != ctx.guild.id:
            await ctx.send(_("That message isn't in this server."))
            return False
        return True

    async def edit_buttons(
        self, ctx: commands.Context, message: discord.Message, view: discord.ui.View | discord.ui.LayoutView
    ) -> bool:
        try:
            await message.edit(view=view)
        except discord.HTTPException as e:
            log.error("Couldn't change the buttons on message %s in %s", message.id, message.channel.id, exc_info=e)
            await ctx.send(_("Discord wouldn't let me change that message's buttons."))
            return False
        return True
