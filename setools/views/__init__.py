import contextlib
import typing as t

import discord
from redbot.core import commands

from ..abc import MixinMeta


class BaseMenu(discord.ui.View):
    def __init__(
        self,
        cog: MixinMeta,
        ctx: commands.Context,
        message: discord.Message = None,
        timeout: int = 240,
    ):
        super().__init__(timeout=timeout)
        self.cog: MixinMeta = cog
        self.ctx: commands.Context = ctx
        self.message: discord.Message | None = message

        self.conf = cog.db.get_conf(ctx.guild)
        self.interaction = ctx.interaction
        self.author: discord.User | discord.Member = ctx.author
        self.channel: discord.TextChannel | discord.ForumChannel | discord.Thread = ctx.channel
        self.guild: discord.Guild | None = ctx.guild

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            try:
                await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            except discord.NotFound:
                pass
            return False

        return True

    async def on_timeout(self) -> None:
        if self.message is not None:
            with contextlib.suppress(discord.HTTPException, discord.NotFound):
                await self.message.edit(view=None)
        self.stop()


class MenuButton(discord.ui.Button):
    def __init__(
        self,
        callback_func: t.Callable,
        style: discord.ButtonStyle = discord.ButtonStyle.primary,
        label: str | None = None,
        disabled: bool = False,
        emoji: str | discord.Emoji | discord.PartialEmoji = None,
        row: int | None = None,
    ):
        super().__init__(
            style=style,
            label=label,
            disabled=disabled,
            emoji=emoji,
            row=row,
        )
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self)
