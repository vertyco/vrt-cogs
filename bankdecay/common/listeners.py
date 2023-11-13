import discord
from redbot.core import commands

from ..abc import MixinMeta


class Listeners(MixinMeta):
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return
        if not message.author:
            return
        if message.author.bot:
            return
        self.db.refresh_user(message.author)
        await self.save()

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        guild = before.guild or after.guild
        if not guild:
            return
        author = before.author or after.author
        if not author:
            return
        if author.bot:
            return
        self.db.refresh_user(author)
        await self.save()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member | discord.User) -> None:
        if not user.guild:
            return
        if user.bot:
            return
        self.db.refresh_user(user)
        await self.save()

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.Member | discord.User) -> None:
        if not user.guild:
            return
        if user.bot:
            return
        self.db.refresh_user(user)
        await self.save()
