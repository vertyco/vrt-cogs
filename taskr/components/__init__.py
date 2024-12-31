from __future__ import annotations

import logging

import discord
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.models import DB

_ = Translator("Taskr", __file__)
log = logging.getLogger("red.vrt.taskr.components")


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        message: discord.Message = None,
        timeout: int = 240,
        delete_on_timeout: bool = False,
    ):
        super().__init__(timeout=timeout)
        self.cog: MixinMeta = ctx.cog
        self.db: DB = self.cog.db
        self.bot: Red = ctx.bot
        self.guild: discord.Guild = ctx.guild
        self.ctx: commands.Context = ctx

        self.interaction = ctx.interaction
        self.author: discord.User | discord.Member = ctx.author
        self.channel: discord.TextChannel | discord.ForumChannel | discord.Thread = ctx.channel
        self.message: discord.Message = message

        self.delete_on_timeout = delete_on_timeout

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        log.error(
            "Error in view %s for item %s with user %s in channel %s",
            type(self).__name__,
            item,
            self.author,
            self.channel,
            exc_info=error,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            try:
                await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            except discord.NotFound:
                pass
            return False

        return True

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                if self.delete_on_timeout:
                    await self.message.delete()
                else:
                    await self.message.edit(view=None)
            except discord.HTTPException:
                try:
                    message = await self.channel.fetch_message(self.message.id)
                    if self.delete_on_timeout:
                        await message.delete()
                    else:
                        await message.edit(view=None)
                except discord.HTTPException:
                    pass
        self.stop()
