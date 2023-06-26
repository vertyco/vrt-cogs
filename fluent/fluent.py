import logging
import traceback
from typing import Optional

import discord
import googletrans
from aiocache import cached
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import pagify

from .api import TranslateManager

translator = googletrans.Translator()
log = logging.getLogger("red.vrt.fluent")
fail_embed = discord.Embed(description="❌ API seems to be down at the moment.")


# Inspired by Obi-Wan3#0003's translation cog.


class Fluent(commands.Cog):
    """
    Seamless translation between two languages in one channel.
    """

    __author__ = "Vertyco"
    __version__ = "1.3.1"

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.translator = TranslateManager()
        self.config = Config.get_conf(self, identifier=11701170)
        default_guild = {"channels": {}}
        self.config.register_guild(**default_guild)

    # Gets language identifier from string
    @staticmethod
    async def converter(language: str):
        for key, value in googletrans.LANGUAGES.items():
            if language == "chinese":
                language = "chinese (simplified)"
            if language == value or language == key:
                return key

    # Cached for two days to minimize api use as much as possible
    @cached(ttl=1800)
    async def translate(self, msg: str, dest: str):
        return await self.translator.translate(msg, dest)

    @commands.hybrid_command(name="translate")
    @app_commands.describe(to_language="Translate to this language")
    @commands.bot_has_permissions(embed_links=True)
    async def translate_command(
        self, ctx: commands.Context, to_language: str, *, message: Optional[str] = None
    ):
        """Translate a message"""
        lang = await self.converter(to_language.lower())
        if not lang:
            return await ctx.send(f"The `{to_language}` was not found")

        if not message and hasattr(ctx.message, "reference"):
            try:
                message = ctx.message.reference.resolved.content
            except AttributeError:
                pass
        if not message:
            return await ctx.send("Could not find any content to translate!")
        try:
            trans = await self.translate(message, lang)
        except Exception as e:
            await ctx.send(f"Translation failed: `{e}`")
            log.error("Translation failed", exc_info=e)
            return
        if trans is None:
            return await ctx.send(embed=fail_embed)

        embed = discord.Embed(description=trans.text, color=ctx.author.color)
        embed.set_footer(text=f"{trans.src} -> {lang}")
        try:
            await ctx.reply(embed=embed, mention_author=False)
        except (discord.NotFound, AttributeError):
            await ctx.send(embed=embed)

    @translate_command.autocomplete("to_language")
    async def translate_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self.get_langs(current)

    @cached(ttl=60)
    async def get_langs(self, current: str):
        return [
            app_commands.Choice(name=i, value=i)
            for i in googletrans.LANGUAGES.values()
            if current.lower() in i.lower()
        ][:45]

    @commands.group()
    @commands.mod()
    async def fluent(self, ctx: commands.Context):
        """Base command"""
        pass

    @fluent.command()
    @commands.bot_has_permissions(embed_links=True)
    async def add(
        self,
        ctx: commands.Context,
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
                    embed=discord.Embed(description="✅ Fluent channel has been set!", color=color)
                )

    @fluent.command(aliases=["delete", "del", "rem"])
    @commands.bot_has_permissions(embed_links=True)
    async def remove(self, ctx: commands.Context, channel: Optional[discord.TextChannel]):
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
                embed = discord.Embed(description=f"❌ {channel.mention} isn't a fluent channel.")
                await ctx.send(embed=embed)

    @fluent.command()
    async def view(self, ctx: commands.Context):
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

        if message.channel.permissions_for(message.guild.me).embed_links:
            embed = discord.Embed(description=trans.text, color=message.author.color)
            try:
                await message.reply(embed=embed, mention_author=False)
            except (discord.NotFound, AttributeError):
                await channel.send(embed=embed)
        else:
            try:
                await message.reply(trans.text, mention_author=False)
            except (discord.NotFound, AttributeError):
                await channel.send(trans.text)

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        """Registers a command with Assistant enabling it to access translations"""
        schema = {
            "name": "get_translation",
            "description": "Translate text to another language",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "the text to translate"},
                    "to_language": {
                        "type": "string",
                        "description": "the target language to translate to",
                    },
                },
                "required": ["message", "to_language"],
            },
        }
        await cog.register_function(cog_name="Fluent", schema=schema)

    async def get_translation(self, message: str, to_language: str, *args, **kwargs) -> str:
        lang = await self.converter(to_language)
        if not lang:
            return "Invalid target language"
        try:
            translation = await self.translate(message, lang)
            return f"{translation.text}\n({translation.src} -> {lang})"
        except Exception as e:
            return f"Error: {e}"
