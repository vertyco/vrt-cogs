import logging

import discord
from redbot.core import commands

from ..abc import MixinMeta
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
        if not conf.api_key:
            return await ctx.send("This command requires an API key from OpenAI to be configured!")
        if not await can_use(ctx.message, conf.blacklist):
            return
        # embed_links perm handled in following functions
        async with ctx.typing():
            await self.handle_message(ctx.message, question, conf)

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
        conversation = self.db.get_conversation(user.id, ctx.channel.id, ctx.guild.id)
        messages = len(conversation.messages)

        def generate_color(index, limit):
            if index > limit:
                return (255, 0, 0)

            # RGB for white is (255, 255, 255) and for red is (255, 0, 0)
            # As we progress from white to red, we need to decrease the values of green and blue from 255 to 0

            # Calculate the decrement in green and blue values
            decrement = int((255 / limit) * index)

            # Calculate the new green and blue values
            green = blue = 255 - decrement

            # Return the new RGB color
            return (green, blue)

        g, b = generate_color(messages, conf.max_retention)
        gg, bb = generate_color(conversation.user_token_count(), conf.max_tokens)
        # Whatever limit is more severe get that color
        color = discord.Color.from_rgb(255, min(g, gg), min(b, bb))

        embed = discord.Embed(
            description=(
                f"{ctx.channel.mention}\n"
                f"`Messages: `{messages}/{conf.max_retention}\n"
                f"`Tokens:   `{conversation.user_token_count()}/{conf.max_tokens}\n"
                f"`Expired:  `{conversation.is_expired(conf)}\n"
                f"`Model:    `{conf.model}"
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
