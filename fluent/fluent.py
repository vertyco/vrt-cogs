import logging
import traceback
from typing import Optional

import discord
import googletrans
from aiocache import SimpleMemoryCache, cached
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify

from .api import TranslateManager

translator = googletrans.Translator()
log = logging.getLogger("red.vrt.fluent")


# Inspired by Obi-Wan3#0003's translation cog.


class Fluent(commands.Cog):
    """
    Seamless translation between two languages in one channel.
    """

    __author__ = "Vertyco"
    __version__ = "1.2.7"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.translator = TranslateManager(bot)
        self.config = Config.get_conf(self, identifier=11701170)
        default_guild = {"channels": {}}
        self.config.register_guild(**default_guild)

    # Gets language identifier from string
    @staticmethod
    async def converter(language: str):
        for key, value in googletrans.LANGUAGES.items():
            if language == "chinese":
                language = "chinese (simplified)"
            if language == value:
                return key

    # Cached for two days to minimize api use as much as possible
    @cached(ttl=172800, cache=SimpleMemoryCache)
    async def translate(self, msg: str, dest: str):
        return await self.translator.translate(msg, dest)

    @commands.group()
    @commands.mod()
    async def fluent(self, ctx):
        """Base command"""
        pass

    @fluent.command()
    async def add(
        self,
        ctx,
        language1: str,
        language2: str,
        channel: Optional[discord.TextChannel],
    ):
        """
        Add a channel and languages to translate between

        Tip: Language 1 is the first to be converted. For example, if you expect most of the conversation to be
        in english, then make english language 2 to use less api calls.
        """
        if not channel:
            channel = ctx.channel
        language1 = await self.converter(language1.lower())
        language2 = await self.converter(language2.lower())
        if not language1 or not language2:
            return await ctx.send(
                f"One of the languages were not found: lang1-{language1} lang2-{language2}"
            )
        async with self.config.guild(ctx.guild).channels() as channels:
            cid = str(channel.id)
            if cid in channels.keys():
                return await ctx.send(
                    embed=discord.Embed(
                        description=f"❌ {channel.mention} is already a fluent channel."
                    )
                )
            else:
                channels[cid] = {"lang1": language1, "lang2": language2}
                color = discord.Color.green()
                return await ctx.send(
                    embed=discord.Embed(
                        description="✅ Fluent channel has been set!", color=color
                    )
                )

    @fluent.command(aliases=["delete", "del", "rem"])
    async def remove(self, ctx, channel: Optional[discord.TextChannel]):
        """Remove a channel from Fluent"""
        if not channel:
            channel = ctx.channel
        async with self.config.guild(ctx.guild).channels() as channels:
            cid = str(channel.id)
            if cid in channels:
                del channels[cid]
                color = discord.Color.green()
                embed = discord.Embed(
                    description="✅ Fluent channel has been deleted!", color=color
                )
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(
                    description=f"❌ {channel.mention} isn't a fluent channel."
                )
                await ctx.send(embed=embed)

    @fluent.command()
    async def view(self, ctx):
        """View all fluent channels"""
        channels = await self.config.guild(ctx.guild).channels()
        msg = ""
        for cid, langs in channels.items():
            channel = ctx.guild.get_channel(int(cid))
            if not channel:
                continue
            l1 = langs["lang1"]
            l2 = langs["lang2"]
            msg += f"{channel.mention} `({l1} <-> {l2})`\n"

        if not msg:
            return await ctx.send("There are no fluent channels at this time")
        final = f"**Fluent Settings**\n{msg.strip()}"
        for p in pagify(final, page_length=1000):
            await ctx.send(p)

    @commands.Cog.listener("on_message_without_command")
    async def message_handler(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if message.content is None:
            return
        if not message.content.strip():
            return

        channels = await self.config.guild(message.guild).channels()
        channel_id = str(message.channel.id)
        if channel_id not in channels:
            return
        lang1 = channels[channel_id]["lang1"]
        lang2 = channels[channel_id]["lang2"]
        channel = message.channel

        # Attempts to translate message into language1.
        try:
            trans = await self.translate(message.content, lang1)
        except Exception:
            log.error(f"Initial translation failed: {traceback.format_exc()}")
            return
        fail_embed = discord.Embed(description="❌ API seems to be down at the moment.")
        if trans is None:
            return await channel.send(embed=fail_embed)
        # If the source language is also language1, translate into language2
        # If source language was language2, this saves api calls because translating gets the source and translation
        if trans.src == lang1:
            try:
                trans = await self.translate(message.content, lang2)
            except Exception:
                log.error(f"Secondary translation failed: {traceback.format_exc()}")
                return
            if trans is None:
                return await channel.send(embed=fail_embed)
        # If src is lang2 then a 2nd api call isn't needed

        if trans.text.lower() == message.content.lower():
            return

        embed = discord.Embed(description=trans.text, color=message.author.color)
        try:
            await message.reply(embed=embed, mention_author=False)
        except (discord.NotFound, AttributeError):
            await channel.send(embed=embed)
