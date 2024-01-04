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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if not payload.member:
            return
        if payload.member.bot:
            return
        self.db.refresh_user(payload.member)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        if not payload.member:
            return
        if payload.member.bot:
            return
        self.db.refresh_user(payload.member)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = before.guild or after.guild
        if not guild:
            return
        author = before or after
        if author.bot:
            return
        self.db.refresh_user(author)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        guild = before.guild or after.guild
        if not guild:
            return
        author = before or after
        if author.bot:
            return
        self.db.refresh_user(author)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if not member.guild:
            return
        if member.bot:
            return
        self.db.refresh_user(member)
