import asyncio
import json
import logging
from io import BytesIO

import discord
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, escape, pagify

from ..abc import MixinMeta
from ..common.calls import request_model
from ..common.constants import READ_EXTENSIONS
from ..common.utils import can_use

log = logging.getLogger("red.vrt.assistant.base")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class Base(MixinMeta):
    @commands.command(name="chathelp")
    async def chat_help(self, ctx: commands.Context):
        """Get help using assistant"""
        txt = (
            _(
                """
# How to Use

### Commands
`[p]convostats` - view your conversation message count/token usage for that convo.
`[p]clearconvo` - reset your conversation for the current channel/thread/forum.
`[p]showconvo` - get a json dump of your current conversation (this is mostly for debugging)
`[p]chat` or `[p]ask` - command prefix for chatting with the bot outside of the live chat, or just @ it.

### Chat Arguments
`[p]chat --last` - resend the last message of the conversation.
`[p]chat --extract` - extract all markdown text to be sent as a separate message.
`[p]chat --outputfile <filename>` - sends the reply as a file instead.

### Argument Use-Cases
`[p]chat --last --outpufile test.py` - output the last message the bot sent as a file.
`[p]chat write a python script to do X... --extract --outputfile test.py` - all code blocks from the output will be sent as a file in addition to the reply.
`[p]chat --last --extract --outputfile test.py` - extract code blocks from the last message to send as a file.

### File Comprehension
Files may be uploaded with the chat command to be included with the question or query, so rather than pasting snippets, the entire file can be uploaded so that you can ask a question about it.
At the moment the bot is capable of reading the following file extensions.
```json
{}
```
If a file has no extension it will still try to read it only if it can be decoded to utf-8.
### Tips
- Replying to someone else's message while using the `[p]chat` command will include their message in *your* conversation, useful if someone says something helpful and you want to include it in your current convo with GPT.
- Replying to a message with a file attachment will have that file be read and included in your conversation. Useful if you upload a file and forget to use the chat command with it, or if someone else uploads a file you want to query the bot with.
- Conversations are *Per* user *Per* channel, so each channel you interact with GPT in is a different convo.
- Talking to the bot like a person rather than a search engine generally yields better results. The more verbose you can be, the better.
- Conversations are persistent, if you want the bot to forget the convo so far, use the `[p]clearconvo` command
        """
            )
            .replace("[p]", ctx.clean_prefix)
            .format(", ".join(READ_EXTENSIONS))
        )
        embed = discord.Embed(description=txt.strip(), color=ctx.me.color)
        await ctx.send(embed=embed)

    @commands.command(
        name="chat",
        aliases=[
            "ask",
            "escribir",
            "razgovor",
            "discuter",
            "plaudern",
            "채팅",
            "charlar",
            "baterpapo",
            "sohbet",
        ],
    )
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
        mem_id = ctx.channel.id if conf.collab_convos else user.id
        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
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

        convo_tokens = await self.count_payload_tokens(conversation.messages, conf, conf.get_user_model(user))
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
                log.warning(_("Could not fetch external model"), exc_info=e)
                pass

        desc = (
            ctx.channel.mention
            + "\n"
            + _("`Messages: `{}/{}\n`Tokens:   `{}/{}\n`Expired:  `{}\n`Model:    `{}").format(
                messages,
                conf.get_user_max_retention(ctx.author),
                convo_tokens,
                max_tokens,
                conversation.is_expired(conf, ctx.author),
                model,
            )
        )
        if conf.collab_convos:
            desc += "\n" + _("*Collabroative conversations are enabled*")
        embed = discord.Embed(
            description=desc,
            color=color,
        )
        embed.set_author(
            name=_("Conversation stats for {}").format(ctx.channel.name if conf.collab_convos else user.display_name),
            icon_url=ctx.guild.icon if conf.collab_convos else user.display_avatar,
        )
        embed.set_footer(text=_("Token limit is a soft cap and excess is trimmed before sending to the api"))
        await ctx.send(embed=embed)

    @commands.command(name="clearconvo")
    @commands.guild_only()
    async def clear_convo(self, ctx: commands.Context):
        """
        Reset your conversation with the bot

        This will clear all message history between you and the bot for this channel
        """
        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else ctx.author.id
        perms = [
            await self.bot.is_mod(ctx.author),
            ctx.channel.permissions_for(ctx.author).manage_messages,
            ctx.author.id in self.bot.owner_ids,
        ]
        if conf.collab_convos and not any(perms):
            txt = _("Only moderators can clear channel conversations when collaborative conversations are enabled!")
            return await ctx.send(txt)
        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        conversation.reset()
        await ctx.send(_("Your conversation in this channel has been reset!"))

    @commands.command(name="query")
    @commands.bot_has_permissions(embed_links=True)
    async def test_embedding_response(self, ctx: commands.Context, *, query: str):
        """
        Fetch related embeddings according to the current settings along with their scores

        You can use this to fine-tune the minimum relatedness for your assistant
        """
        conf = self.db.get_conf(ctx.guild)
        if not conf.embeddings:
            return await ctx.send(_("You do not have any embeddings configured!"))
        if not conf.top_n:
            return await ctx.send(_("Top N is set to 0 so no embeddings will be returned"))
        if not await self.can_call_llm(conf, ctx):
            return
        async with ctx.typing():
            query_embedding = await self.request_embedding(query, conf)
            if not query_embedding:
                return await ctx.send(_("Failed to get embedding for your query"))

            embeddings = await asyncio.to_thread(conf.get_related_embeddings, query_embedding)
            if not embeddings:
                return await ctx.send(_("No embeddings could be related to this query with the current settings"))
            for name, em, score, dimension in embeddings:
                for p in pagify(em, page_length=4000):
                    txt = (
                        _("`Entry Name:  `{}\n").format(name)
                        + _("`Relatedness: `{}\n").format(round(score, 4))
                        + _("`Dimensions:  `{}\n").format(dimension)
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
        conf = self.db.get_conf(ctx.guild)
        mem_id = ctx.channel.id if conf.collab_convos else user.id
        conversation = self.db.get_conversation(mem_id, ctx.channel.id, ctx.guild.id)
        if not conversation.messages:
            return await ctx.send(_("You have no conversation in this channel!"))

        text = ""
        for message in conversation.messages:
            text += f"{json.dumps(message, indent=2)}\n"

        buffer = BytesIO(text.encode())
        buffer.name = f"{ctx.author.name}_transcript.txt"
        buffer.seek(0)
        file = discord.File(buffer)
        await ctx.send(_("Here is your conversation transcript!"), file=file)
