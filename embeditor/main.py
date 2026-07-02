import logging

import discord
from discord import app_commands
from redbot.core import commands
from redbot.core.bot import Red

from .common.checks import edit_error
from .common.editor import EditorSession
from .common.quick import QuickEditModal

log = logging.getLogger("red.vrt.embeditor")


@app_commands.context_menu(name="Quick Edit")
@app_commands.default_permissions(administrator=True)
async def quick_edit_message(interaction: discord.Interaction, message: discord.Message):
    error = await edit_error(interaction, message)
    if error:
        return await interaction.response.send_message(error, ephemeral=True)
    if message.flags.components_v2:
        return await interaction.response.send_message(
            "This message uses v2 components, use Full Edit instead.", ephemeral=True
        )
    if not message.content and len(message.embeds) != 1:
        return await interaction.response.send_message(
            "This message has nothing Quick Edit can work with, use Full Edit instead.", ephemeral=True
        )
    await interaction.response.send_modal(QuickEditModal(message))


@app_commands.context_menu(name="Full Edit")
@app_commands.default_permissions(administrator=True)
async def full_edit_message(interaction: discord.Interaction, message: discord.Message):
    error = await edit_error(interaction, message)
    if error:
        return await interaction.response.send_message(error, ephemeral=True)
    perms = message.channel.permissions_for(interaction.guild.me)
    if not perms.send_messages or not perms.embed_links:
        return await interaction.response.send_message(
            "I need send messages and embed links permissions in this channel to open the editor.", ephemeral=True
        )
    session = EditorSession(interaction, message)
    await session.start(interaction)


class Embeditor(commands.Cog):
    """
    Easily edit any message sent by the bot.

    Adds two message context menu commands for admins:
    - **Quick Edit**: a modal pre-filled with the message's existing parts.
    - **Full Edit**: an interactive editor posted below the message with full
      control over content, embed parts, fields, and v2 text containers.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "1.0.0"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot = bot

    def format_help_for_context(self, ctx: commands.Context) -> str:
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nVersion: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """This cog stores no user data."""
