from contextlib import suppress

import discord
from redbot.core import commands

from ..abc import MixinMeta


class BaseView(discord.ui.View):
    def __init__(self, cog: MixinMeta, ctx: commands.Context):
        super().__init__(timeout=600)
        self.cog = cog
        self.ctx = ctx

        self.conf = cog.db.get_conf(ctx.guild)
        self.channel = ctx.channel
        self.guild = ctx.guild
        self.author = ctx.author
        self.message: discord.Message = None

    async def on_timeout(self) -> None:
        if self.message:
            with suppress(discord.HTTPException):
                await self.message.delete()
                await self.ctx.tick()
        self.stop()
        await self.cog.save()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False

        return True
