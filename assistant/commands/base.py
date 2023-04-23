import logging

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.assistant.base")


class Base(MixinMeta):
    @commands.command(name="chat")
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ask_question(self, ctx: commands.Context, *, question: str):
        """Ask [botname] a question!"""
        conf = self.db.get_conf(ctx.guild)
        async with ctx.typing():
            try:
                reply = await self.get_chat_response(
                    question, ctx.author, conf
                )
                parts = [p for p in pagify(reply, page_length=2000)]
                for index, p in enumerate(parts):
                    if not index:
                        await ctx.reply(p, mention_author=conf.mention)
                    else:
                        await ctx.send(p)
            except Exception as e:
                await ctx.send(f"**Error**\n```py\n{e}\n```")

    @commands.command(name="tokencount")
    @commands.guild_only()
    async def token_count(
        self, ctx: commands.Context, *, user: discord.Member = None
    ):
        """Check the token and message count of yourself or another user's conversation"""
        if not user:
            user = ctx.author
        conf = self.db.get_conf(ctx.guild)
        conversation = self.chats.get_conversation(user)
        messages = len(conversation.messages)
        embed = discord.Embed(
            title="Token Usage",
            description=(
                f"`Messages: `{messages}\n"
                f"`Tokens:   `{conversation.token_count}\n"
                f"`Expired:  `{conversation.is_expired(conf)}"
            ),
            color=user.color,
        )
        await ctx.send(embed=embed)
