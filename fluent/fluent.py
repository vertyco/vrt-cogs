import logging
import typing as t

import discord
from aiocache import cached
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify

from .common.api import Result, TranslateManager
from .common.constants import available_langs

log = logging.getLogger("red.vrt.fluent")
_ = Translator("Fluent", __file__)


# redgettext -D fluent.py --command-docstring
@cog_i18n(_)
class Fluent(commands.Cog):
    """
    Seamless translation between two languages in one channel. Or manual translation to various languages.

    Fluent uses google translate by default, with [Flowery](https://flowery.pw/) as a fallback.

    Fluent also supports the [Deepl](https://www.deepl.com/pro#developer) tranlsation api.
    1. Register your free Deepl account **[Here](https://www.deepl.com/pro#developer)**.
    2. Obtain your API key **[Here](https://www.deepl.com/account/summary)**.
    3. Set your API key with:
    `[p]set api deepl key YOUR_KEY_HERE`

    If a deepl key is set, it will use that before falling back to google translate and then flowery.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "2.1.5"

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return _("{}\nCog Version: {}\nAuthor: {}").format(helpcmd, self.__version__, self.__author__)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=11701170)
        self.config.register_guild(channels={})
        logging.getLogger("hpack.hpack").setLevel(logging.INFO)
        logging.getLogger("deepl").setLevel(logging.WARNING)

    @cached(ttl=10)
    async def get_channels(self, guild: discord.Guild) -> dict:
        return await self.config.guild(guild).channels()

    @cached(ttl=900)
    async def translate(self, msg: str, dest: str, force: bool = False) -> Result:
        deepl_key = await self.bot.get_shared_api_tokens("deepl")
        translator = TranslateManager(deepl_key=deepl_key.get("key"))
        return await translator.translate(msg, dest, force=force)

    @commands.hybrid_command(name="translate")
    @app_commands.describe(to_language="Translate to this language")
    @commands.bot_has_permissions(embed_links=True)
    async def translate_command(self, ctx: commands.Context, to_language: str, *, message: t.Optional[str] = None):
        """Translate a message"""
        translator = TranslateManager()
        lang = await translator.get_lang(to_language)
        if not lang:
            txt = _("The target language `{}` was not found.").format(to_language)
            return await ctx.send(txt)

        if not message and hasattr(ctx.message, "reference"):
            try:
                message = ctx.message.reference.resolved.content
            except AttributeError:
                pass
        if not message:
            txt = _("Could not find any content to translate!")
            return await ctx.send(txt)

        try:
            trans: t.Optional[Result] = await self.translate(message, to_language)
        except Exception as e:
            txt = _("An error occured while translating, Check logs for more info.")
            await ctx.send(txt)
            log.error("Translation failed", exc_info=e)
            self.bot._last_exception = e
            return

        if trans is None:
            txt = _("❌ Translation failed.")
            return await ctx.send(txt)

        embed = discord.Embed(description=trans.text, color=ctx.author.color)
        embed.set_footer(text=f"{trans.src} -> {trans.dest}")
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
            app_commands.Choice(name=i["name"], value=i["name"])
            for i in available_langs
            if current.lower() in i["name"].lower()
        ][:25]

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
        channel: t.Optional[
            t.Union[
                discord.TextChannel,
                discord.Thread,
                discord.ForumChannel,
            ]
        ] = None,
    ):
        """
        Add a channel and languages to translate between

        Tip: Language 1 is the first to be converted. For example, if you expect most of the conversation to be
        in english, then make english language 2 to use less api calls.
        """
        if not channel:
            channel = ctx.channel

        if language1.lower() == language2.lower():
            txt = _("You can't use the same language for both parameters. {} to {} is still {}...").format(
                language1, language1, language1
            )
            return await ctx.send(txt)

        translator = TranslateManager()
        lang1 = await translator.get_lang(language1)
        lang2 = await translator.get_lang(language2)

        if not lang1 and not lang2:
            txt = _("Both of those languages are invalid.")
            return await ctx.send(txt)
        if not lang1:
            txt = _("Language 1 is invalid.")
            return await ctx.send(txt)
        if not lang2:
            txt = _("Language 2 is invalid.")
            return await ctx.send(txt)

        async with self.config.guild(ctx.guild).channels() as channels:
            cid = str(channel.id)
            if cid in channels.keys():
                txt = _("❌ {} is already a fluent channel.").format(channel.mention)
                return await ctx.send(txt)
            else:
                channels[cid] = {"lang1": language1, "lang2": language2}
                txt = _("✅ Fluent channel has been set!")
                return await ctx.send(txt)

    @fluent.command(aliases=["delete", "del", "rem"])
    @commands.bot_has_permissions(embed_links=True)
    async def remove(
        self,
        ctx: commands.Context,
        channel: t.Optional[
            t.Union[
                discord.TextChannel,
                discord.Thread,
                discord.ForumChannel,
            ]
        ] = None,
    ):
        """Remove a channel from Fluent"""
        if not channel:
            channel = ctx.channel

        async with self.config.guild(ctx.guild).channels() as channels:
            cid = str(channel.id)
            if cid in channels:
                del channels[cid]
                return await ctx.send(_("✅ Fluent channel has been deleted!"))

            await ctx.send(_("❌ {} isn't a fluent channel!").format(channel.mention))

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
            return await ctx.send(_("There are no fluent channels at this time."))
        final = _("**Fluent Settings**\n{}").format(msg.strip())
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
        if not message.channel:
            return
        if not message.content.strip():
            return

        channels = await self.get_channels(message.guild)
        channel_id = str(message.channel.id)
        if channel_id not in channels:
            return

        lang1 = channels[channel_id]["lang1"]
        lang2 = channels[channel_id]["lang2"]
        log.debug(f"Translating... {lang1} <-> {lang2}")

        channel = message.channel
        async with channel.typing():
            # Attempts to translate message into language1.
            try:
                trans = await self.translate(message.content, lang1, force=True)
            except Exception as e:
                log.error("Initial listener translation failed", exc_info=e)
                self.bot._last_exception = e
                return

            if trans is None:
                log.debug("Auto translation first phase returned None")
                return

            translator = TranslateManager()
            source = await translator.get_lang(trans.src)
            source = source.split("-")[0].lower()
            target = await translator.get_lang(lang1)
            target = target.split("-")[0].lower()
            log.debug(f"Source: {source}, target: {target}")
            log.debug(f"Raw Source: {trans.src}")

            # If the source language is also language1, translate into language2
            # If source language was language2, this saves api calls because translating gets the source and translation
            if source == target:
                try:
                    trans = await self.translate(message.content, lang2)
                except Exception as e:
                    log.error("Secondary listener translation failed", exc_info=e)
                    return

                if trans is None:
                    return await channel.send(_("Unable to finish translation, perhaps the API is down."))

            # If translated text is the same as the source, no need to send
            if trans.text.lower() == message.content.lower():
                log.debug("Translated text is the same as the source, no need to send")
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
        translator = TranslateManager()
        lang = await translator.get_lang(to_language)
        if not lang:
            return _("Invalid target language")
        try:
            translation = await self.translate(message, lang)
            return f"{translation.text}\n({translation.src} -> {lang})"
        except Exception as e:
            return f"Error: {e}"
