import logging

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import pagify

from ..abc import MixinMeta
from ..common.utils import get_attachments
from ..models import READ_EXTENSIONS

log = logging.getLogger("red.vrt.assistant.base")


class Base(MixinMeta):
    @commands.command(name="chat")
    @commands.guild_only()
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def ask_question(self, ctx: commands.Context, *, question: str):
        """
        Chat with [botname]!

        Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.api_key:
            return await ctx.send("This command requires an API key from OpenAI to be configured!")
        async with ctx.typing():
            if attachments := get_attachments(ctx.message):
                for i in attachments:
                    has_extension = i.filename.count(".") > 0
                    if (
                        not any(i.filename.lower().endswith(ext) for ext in READ_EXTENSIONS)
                        and has_extension
                    ):
                        continue
                    file_bytes = await i.read()
                    if has_extension:
                        text = file_bytes.decode()
                    else:
                        text = file_bytes
                    question += f"\n\nUploaded [{i.filename}]: {text}"
            try:
                reply = await self.get_chat_response(
                    question, ctx.author, ctx.guild, ctx.channel, conf
                )
                if len(reply) < 2000:
                    return await ctx.reply(reply, mention_author=conf.mention)

                embeds = [discord.Embed(description=p) for p in pagify(reply, page_length=4000)]
                await ctx.reply(embeds=embeds, mention_author=conf.mention)

            except Exception as e:
                await ctx.send(f"**Error**\n```py\n{e}\n```")
                log.error("Chat command failed", exc_info=e)

    @commands.command(name="convostats")
    @commands.guild_only()
    async def token_count(self, ctx: commands.Context, *, user: discord.Member = None):
        """
        Check the token and message count of yourself or another user's conversation for this channel

        Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel

        Conversations are only stored in memory until the bot restarts or the cog reloads
        """
        if not user:
            user = ctx.author
        conf = self.db.get_conf(ctx.guild)
        conversation = self.chats.get_conversation(user.id, ctx.channel.id, ctx.guild.id)
        messages = len(conversation.messages)
        embed = discord.Embed(
            description=(
                f"**Conversation stats for {user.mention} in {ctx.channel.mention}**\n"
                f"`Messages: `{messages}\n"
                f"`Tokens:   `{conversation.user_token_count()}\n"
                f"`Expired:  `{conversation.is_expired(conf)}"
            ),
            color=user.color,
        )
        await ctx.send(embed=embed)

    @commands.command(name="clearconvo")
    @commands.guild_only()
    async def clear_convo(self, ctx: commands.Context):
        """
        Reset your conversation

        This will clear all message history between you and the bot for this channel
        """
        conversation = self.chats.get_conversation(ctx.author.id, ctx.channel.id, ctx.guild.id)
        conversation.reset()
        await ctx.tick()
