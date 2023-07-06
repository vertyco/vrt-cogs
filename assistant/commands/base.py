import asyncio
import logging
from io import BytesIO

import discord
from redbot.core import commands
from redbot.core.utils.chat_formatting import box, escape, pagify

from ..abc import MixinMeta
from ..common.calls import request_model
from ..common.utils import can_use

log = logging.getLogger("red.vrt.assistant.base")


class Base(MixinMeta):
    @commands.command(name="chat", aliases=["ask"])
    @commands.guild_only()
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def ask_question(self, ctx: commands.Context, *, question: str):
        """
        Chat with [botname]!

        Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel

        **Optional Arguments**
        `--outputfile <filename>` - uploads a file with the reply instead (no spaces)
        `--extract` - extracts code blocks from the reply

        **Example**
        `[p]chat write a python script that prints "Hello World!"`
        - Including `--outputfile hello.py` will output a file containing the whole response.
        - Including `--outputfile hello.py --extract` will output a file containing just the code blocks and send the rest as text.
        - Including `--extract` will send the code separately from the reply
        """
        conf = self.db.get_conf(ctx.guild)
        if not await self.can_call_llm(conf, ctx):
            return
        if not await can_use(ctx.message, conf.blacklist):
            return
        async with ctx.typing():
            await self.handle_message(ctx.message, question, conf)

    @commands.command(name="convostats")
    @commands.guild_only()
    async def show_convo_stats(self, ctx: commands.Context, *, user: discord.Member = None):
        """
        Check the token and message count of yourself or another user's conversation for this channel

        Conversations are *Per* user *Per* channel, meaning a conversation you have in one channel will be kept in memory separately from another conversation in a separate channel

        Conversations are only stored in memory until the bot restarts or the cog reloads
        """
        if not user:
            user = ctx.author
        conf = self.db.get_conf(ctx.guild)
        conversation = self.db.get_conversation(user.id, ctx.channel.id, ctx.guild.id)
        messages = len(conversation.messages)

        max_tokens = self.get_max_tokens(conf, ctx.author)

        def generate_color(index: int, limit: int):
            if not limit:
                return (0, 0)
            if index > limit:
                return (0, 0)

            # RGB for white is (255, 255, 255) and for red is (255, 0, 0)
            # As we progress from white to red, we need to decrease the values of green and blue from 255 to 0

            # Calculate the decrement in green and blue values
            decrement = int((255 / limit) * index)

            # Calculate the new green and blue values
            green = blue = 255 - decrement

            # Return the new RGB color
            return (green, blue)

        convo_tokens = await self.convo_token_count(conf, conversation)
        g, b = generate_color(messages, conf.get_user_max_retention(ctx.author))
        gg, bb = generate_color(convo_tokens, max_tokens)
        # Whatever limit is more severe get that color
        color = discord.Color.from_rgb(255, min(g, gg), min(b, bb))
        model = conf.get_user_model(ctx.author)
        if not conf.api_key and (conf.endpoint_override or self.db.endpoint_override):
            endpoint = conf.endpoint_override or self.db.endpoint_override
            try:
                res = await request_model(f"{endpoint}/model")
                model = res["model"]
            except Exception as e:  # Could be any issue, don't worry about it here
                log.warning("Could not fetch external model", exc_info=e)
                pass

        embed = discord.Embed(
            description=(
                f"{ctx.channel.mention}\n"
                f"`Messages: `{messages}/{conf.get_user_max_retention(ctx.author)}\n"
                f"`Tokens:   `{convo_tokens}/{max_tokens}\n"
                f"`Expired:  `{conversation.is_expired(conf, ctx.author)}\n"
                f"`Model:    `{model}"
            ),
            color=color,
        )
        embed.set_author(
            name=f"Conversation stats for {user.display_name}", icon_url=user.display_avatar
        )
        embed.set_footer(
            text="Token limit is a soft cap and excess is trimmed before sending to the api"
        )
        await ctx.send(embed=embed)

    @commands.command(name="clearconvo")
    @commands.guild_only()
    async def clear_convo(self, ctx: commands.Context):
        """
        Reset your conversation with the bot

        This will clear all message history between you and the bot for this channel
        """
        conversation = self.db.get_conversation(ctx.author.id, ctx.channel.id, ctx.guild.id)
        conversation.reset()
        await ctx.send("Your conversation in this channel has been reset!")

    @commands.command(name="query")
    @commands.bot_has_permissions(embed_links=True)
    async def test_embedding_response(self, ctx: commands.Context, *, query: str):
        """
        Fetch related embeddings according to the current settings along with their scores

        You can use this to fine-tune the minimum relatedness for your assistant
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.embeddings:
            return await ctx.send("You do not have any embeddings configured!")
        if not await self.can_call_llm(conf, ctx):
            return
        async with ctx.typing():
            query_embedding = await self.request_embedding(query, conf)
            if not query_embedding:
                return await ctx.send("Failed to get embedding for your query")

            embeddings = await asyncio.to_thread(conf.get_related_embeddings, query_embedding)
            if not embeddings:
                return await ctx.send(
                    "No embeddings could be related to this query with the current settings"
                )
            for name, em, score, dimension in embeddings:
                for p in pagify(em, page_length=4000):
                    txt = (
                        f"`Entry Name:  `{name}\n"
                        f"`Relatedness: `{round(score, 4)}\n"
                        f"`Dimensions:  `{dimension}\n"
                    )
                    escaped = escape(p)
                    boxed = box(escaped)
                    txt += boxed
                    embed = discord.Embed(description=txt)
                    await ctx.send(embed=embed)

    @commands.command(name="showconvo")
    @commands.guild_only()
    @commands.guildowner()
    async def show_convo(self, ctx: commands.Context, *, user: discord.Member = None):
        """
        View the current transcript of a conversation

        This is mainly here for moderation purposes
        """
        if not user:
            user = ctx.author
        conversation = self.db.get_conversation(user.id, ctx.channel.id, ctx.guild.id)
        if not conversation.messages:
            return await ctx.send("You have no conversation in this channel!")

        text = ""
        for message in conversation.messages:
            role = message["role"]
            content = message["content"]
            text += f"{role}: {content}\n"

        buffer = BytesIO(text.encode())
        buffer.name = f"{ctx.author.name}_transcript.txt"
        buffer.seek(0)
        file = discord.File(buffer)
        await ctx.send("Here is your conversation transcript!", file=file)
