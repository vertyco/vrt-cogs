import asyncio
import logging
import typing as t
from collections import defaultdict
from contextlib import suppress

import discord
from aiocache import cached
from discord import app_commands
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.views import SetApiView

from .abc import CompositeMetaClass
from .common import api, constants, models
from .views import TranslateMenu

log = logging.getLogger("red.vrt.fluent")
_ = Translator("Fluent", __file__)


class AssistantRegistry(t.Protocol):
    async def register_function(
        self,
        cog_name: str,
        schema: dict,
        permission_level: t.Literal["user", "mod", "admin", "owner"] = "user",
        category: t.Optional[str] = None,
        requires_user_approval: bool = False,
    ) -> bool: ...


@app_commands.context_menu(name="Translate")
async def translate_message_ctx(interaction: discord.Interaction, message: discord.Message):
    """Translate a message"""
    if not message.content and not message.embeds:
        return await interaction.response.send_message(_("❌ No content to translate."), ephemeral=True)
    with suppress(discord.HTTPException):
        await interaction.response.defer(ephemeral=True, thinking=True)
    bot: Red = interaction.client
    cog = t.cast(t.Optional[Fluent], bot.get_cog("Fluent"))
    if cog is None or message.guild is None:
        return await interaction.edit_original_response(content=_("❌ Translation failed."))
    target_lang = message.guild.preferred_locale.value
    working_embeds = [embed.copy() for embed in message.embeds]

    to_translate = []
    if message.content:
        to_translate.append(("content", message.content))
    for embed_idx, embed in enumerate(working_embeds):
        if embed.author and embed.author.name:
            to_translate.append((f"embed_{embed_idx}_author_name", embed.author.name))
        if embed.title:
            to_translate.append((f"embed_{embed_idx}_title", embed.title))
        if embed.description:
            to_translate.append((f"embed_{embed_idx}_desc", embed.description))
        if embed.footer and embed.footer.text:
            to_translate.append((f"embed_{embed_idx}_footer", embed.footer.text))
        for field_idx, field in enumerate(embed.fields):
            to_translate.append((f"embed_{embed_idx}_field_{field_idx}_name", field.name))
            to_translate.append((f"embed_{embed_idx}_field_{field_idx}_value", field.value))

    if not to_translate:
        return await interaction.edit_original_response(content=_("❌ No content to translate."))

    tasks_dict = {key: cog.translate(text, target_lang) for key, text in to_translate}
    results = await asyncio.gather(*tasks_dict.values())
    translation_map = dict(zip(tasks_dict.keys(), results))

    first_result: t.Optional[api.Result] = next((r for r in results if r is not None), None)
    if first_result is None:
        return await interaction.edit_original_response(content=_("❌ Translation failed."))

    translated_content = None
    if message.content:
        res = translation_map.get("content")
        translated_content = (res.text if res else message.content)[:2000]

    new_embeds = []
    for embed_idx, embed in enumerate(working_embeds):
        new_embed = embed.copy()
        if new_embed.author and new_embed.author.name:
            author_name = translation_map.get(f"embed_{embed_idx}_author_name")
            new_embed.set_author(
                name=(author_name.text if author_name else new_embed.author.name)[:256],
                url=new_embed.author.url,
                icon_url=new_embed.author.icon_url,
            )
        if new_embed.title:
            title = translation_map.get(f"embed_{embed_idx}_title")
            new_embed.title = (title.text if title else new_embed.title)[:256]
        if new_embed.description:
            description = translation_map.get(f"embed_{embed_idx}_desc")
            new_embed.description = (description.text if description else new_embed.description)[:4096]
        if new_embed.footer and new_embed.footer.text:
            footer = translation_map.get(f"embed_{embed_idx}_footer")
            new_embed.set_footer(
                text=(footer.text if footer else new_embed.footer.text)[:2048],
                icon_url=new_embed.footer.icon_url,
            )
        fields = new_embed.fields.copy()
        new_embed.clear_fields()
        for field_idx, field in enumerate(fields):
            name_translation = translation_map.get(f"embed_{embed_idx}_field_{field_idx}_name")
            value_translation = translation_map.get(f"embed_{embed_idx}_field_{field_idx}_value")
            field_name = t.cast(str, name_translation.text if name_translation else field.name)
            field_value = t.cast(str, value_translation.text if value_translation else field.value)
            new_embed.add_field(
                name=field_name[:256],
                value=field_value[:1024],
                inline=field.inline,
            )
        new_embeds.append(new_embed)

    if new_embeds:
        last = new_embeds[-1]
        if not last.footer or not last.footer.text:
            last.set_footer(text=f"{first_result.src} -> {first_result.dest}")
        await interaction.edit_original_response(content=translated_content, embeds=new_embeds)
    else:
        embed = discord.Embed(
            description=translated_content,
            color=await bot.get_embed_color(message),
        ).set_footer(text=f"{first_result.src} -> {first_result.dest}")
        await interaction.edit_original_response(content=None, embed=embed)


# redgettext -D fluent/fluent.py --command-docstring
@cog_i18n(_)
class Fluent(commands.Cog, metaclass=CompositeMetaClass):
    """
    Seamless translation between two languages in one channel. Or manual translation to various languages.

    Fluent uses google translate by default, with [Flowery](https://flowery.pw/) as a fallback.

    Fluent also supports Deeple and OpenAI for translations.
    Use `[p]fluent openai` and `[p]fluent deepl` to set your keys.

    Fallback order (If translation fails):
    1. OpenAI
    2. Deepl
    3. Google Translate
    4. Flowery
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "2.7.0"

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return _("{}\nCog Version: {}\nAuthor: {}").format(helpcmd, self.__version__, self.__author__)

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=11701170)
        self.config.register_guild(channels={}, buttons=[])
        logging.getLogger("hpack.hpack").setLevel(logging.INFO)
        logging.getLogger("deepl").setLevel(logging.WARNING)
        logging.getLogger("aiocache").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)

    @property
    def _rpc_handlers(self) -> tuple:
        # Single source of truth so cog_load registers and cog_unload unregisters
        # the same set. Unregister-first on load lets a plain reload swap the
        # handlers live. Wire names are the method name uppercased:
        # FLUENT__RPC_ADD_TRANSLATE_BUTTON etc.
        return (
            self.rpc_add_translate_button,
            self.rpc_remove_translate_button,
            self.rpc_list_translate_buttons,
        )

    async def cog_load(self):
        self.bot.tree.add_command(translate_message_ctx)
        for handler in self._rpc_handlers:
            try:
                self.bot.unregister_rpc_handler(handler)
            except Exception:
                pass
            self.bot.register_rpc_handler(handler)
        asyncio.create_task(self.initialize())

    async def cog_unload(self):
        self.bot.tree.remove_command(translate_message_ctx)
        for handler in self._rpc_handlers:
            try:
                self.bot.unregister_rpc_handler(handler)
            except Exception:
                pass

    async def initialize(self):
        await self.bot.wait_until_red_ready()
        for guild in self.bot.guilds:
            await self.init_buttons(guild)

    async def init_buttons(self, guild: discord.Guild, target_message_id: int = None):
        buttons = await self.get_buttons(guild)
        if not buttons:
            return
        buttons.sort(key=lambda x: x.button_text.lower())
        log.info(f"Initializing {len(buttons)} buttons for {guild}")

        # {channel_id: {message_id: [buttons]}}
        button_dict: dict[int, dict[int, list[models.TranslateButton]]] = defaultdict(dict)
        for button in buttons:
            if button.message_id not in button_dict[button.channel_id]:
                button_dict[button.channel_id][button.message_id] = []
            button_dict[button.channel_id][button.message_id].append(button)
        for channel_id, messages in button_dict.items():
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue
            if not isinstance(channel, discord.abc.Messageable):
                continue
            for message_id, button_objs in messages.items():
                if target_message_id and message_id != target_message_id:
                    continue
                view = TranslateMenu(self, button_objs)
                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    continue
                log.info(f"Adding {len(button_objs)} buttons to message {message_id}")
                with suppress(discord.HTTPException):
                    await message.edit(view=view)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild:
            return
        buttons = await self.get_buttons(message.guild)
        if not buttons:
            return
        to_delete = [b for b in buttons if b.message_id == message.id]
        if not to_delete:
            return
        keep = [b.model_dump() for b in buttons if b not in to_delete]
        await self.config.guild(message.guild).buttons.set(keep)
        log.info(f"Removed {len(to_delete)} buttons for message {message.id}")

    # Make sure to handle when a channel is deleted
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not channel.guild:
            return
        buttons = await self.get_buttons(channel.guild)
        if buttons:
            to_delete = [b for b in buttons if b.channel_id == channel.id]
            if to_delete:
                keep = [b.model_dump() for b in buttons if b not in to_delete]
                await self.config.guild(channel.guild).buttons.set(keep)
                log.info(f"Removed {len(to_delete)} buttons for channel {channel.id}")

        # Also remove the channel from fluent channels config if it exists
        async with self.config.guild(channel.guild).channels() as channels:
            cid = str(channel.id)
            if cid in channels:
                del channels[cid]
                log.info(f"Removed fluent channel config for {channel.id}")

    @cached(ttl=10)
    async def get_channels(self, guild: discord.Guild) -> dict:
        return await self.config.guild(guild).channels()

    async def get_buttons(self, guild: discord.Guild) -> list[models.TranslateButton]:
        buttons = await self.config.guild(guild).buttons()
        button_objs = [models.TranslateButton.model_validate(b) for b in buttons]
        return list(set(button_objs))

    @cached(ttl=900)
    async def translate(self, msg: str, dest: str, force: bool = False) -> t.Optional[api.Result]:
        """Get the translation of a message

        Args:
            msg (str): the message to be translated
            dest (str): the target language
            force (bool, optional): If False, force res back to None if api.Result is same as source text. Defaults to False.

        Returns:
            t.Optional[api.Result]: api.Result object containing source/target lang and translated text
        """
        deepl_key = await self.bot.get_shared_api_tokens("fluent_deepl")
        openai_key = await self.bot.get_shared_api_tokens("fluent_openai")
        translator = api.TranslateManager(
            deepl_key=deepl_key.get("key"),
            openai_key=openai_key.get("key"),
        )
        return await translator.translate(msg, dest, force=force)

    @commands.command(name="serverlocale")
    async def server_locale(self, ctx: commands.Context):
        """Check the current server's locale"""
        locale = ctx.guild.preferred_locale
        await ctx.send(f"Server locale is set to: {locale.name} - {locale.value}")

    @commands.hybrid_command(name="translate")
    @app_commands.describe(to_language="Translate to this language")
    @commands.bot_has_permissions(embed_links=True)
    async def translate_command(self, ctx: commands.Context, to_language: str, *, message: t.Optional[str] = None):
        """Translate a message"""
        if ctx.interaction is not None:
            await ctx.interaction.response.defer()
        translator = api.TranslateManager()
        lang = await translator.get_lang(to_language)
        if not lang:
            txt = _("The target language `{}` was not found.").format(to_language)
            return await ctx.send(txt)

        if not message and hasattr(ctx.message, "reference"):
            try:
                resolved = ctx.message.reference.resolved
                if isinstance(resolved, discord.Message):
                    message = resolved.content
            except AttributeError:
                pass
        if not message:
            txt = _("Could not find any content to translate!")
            return await ctx.send(txt)

        try:
            trans: t.Optional[api.Result] = await self.translate(message, to_language)
        except Exception as e:
            txt = _("An error occured while translating, Check logs for more info.")
            await ctx.send(txt)
            log.error("Translation failed", exc_info=e)
            setattr(self.bot, "_last_exception", e)
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
            for i in constants.available_langs
            if current.lower() in i["name"].lower()
        ][:25]

    @commands.group()
    @commands.mod_or_permissions(manage_messages=True)
    async def fluent(self, ctx: commands.Context):
        """Base command"""
        pass

    async def add_translate_button(
        self,
        guild: discord.Guild,
        channel_id: int,
        message_id: int,
        target_lang: str,
        button_text: str,
    ) -> str:
        """Shared add-button logic for the addbutton command and RPC.

        Returns a status string: "added", "exists", or "invalid_lang".
        """
        buttons = await self.get_buttons(guild)
        for b in buttons:
            if b.message_id == message_id and b.target_lang == target_lang:
                return "exists"

        translator = api.TranslateManager()
        lang = await translator.get_lang(target_lang)
        if not lang:
            return "invalid_lang"

        button = models.TranslateButton(
            channel_id=channel_id,
            message_id=message_id,
            target_lang=target_lang,
            button_text=button_text,
        )
        async with self.config.guild(guild).buttons() as raw_buttons:
            raw_buttons.append(button.model_dump())

        await self.init_buttons(guild, target_message_id=message_id)
        return "added"

    async def remove_translate_button(
        self,
        guild: discord.Guild,
        channel_id: int,
        message_id: int,
        target_lang: str,
    ) -> str:
        """Shared remove-button logic for the removebutton command and RPC.

        Returns a status string: "removed" or "not_found".
        """
        buttons = await self.get_buttons(guild)
        found = any(b.message_id == message_id and b.target_lang == target_lang for b in buttons)
        if not found:
            return "not_found"

        # Remove the view from the message if this was its only button
        if len([x for x in buttons if x.message_id == message_id]) == 1:
            channel = self.bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.abc.Messageable):
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(view=None)
                except (discord.NotFound, discord.HTTPException):
                    pass

        async with self.config.guild(guild).buttons() as raw_buttons:
            for idx, b in enumerate(raw_buttons):
                if b.get("message_id") == message_id and b.get("target_lang") == target_lang:
                    del raw_buttons[idx]
                    break

        await self.init_buttons(guild, target_message_id=message_id)
        return "removed"

    @fluent.command()
    async def addbutton(
        self,
        ctx: commands.Context,
        message: discord.Message,
        target_lang: str,
        *,
        button_text: str,
    ):
        """Add a translation button to a message"""
        status = await self.add_translate_button(
            ctx.guild, message.channel.id, message.id, target_lang, button_text
        )
        if status == "exists":
            return await ctx.send(_("That message already has a translation button for that language."))
        if status == "invalid_lang":
            txt = _("Target language is invalid.")
            return await ctx.send(txt)
        await ctx.send(_("Button added successfully to {} for {}").format(message.jump_url, target_lang))

    @fluent.command()
    async def removebutton(self, ctx: commands.Context, message: discord.Message, target_lang: str):
        """Remove a translation button from a message"""
        status = await self.remove_translate_button(ctx.guild, message.channel.id, message.id, target_lang)
        if status == "not_found":
            return await ctx.send(_("No button found for that message."))
        await ctx.send(_("Button removed successfully from {}").format(message.jump_url))

    @fluent.command()
    async def resetbuttontranslations(self, ctx: commands.Context):
        """Reset the translations for saved buttons, to force a re-translation"""
        buttons = await self.get_buttons(ctx.guild)
        for button in buttons:
            button.translated_content = None
            button.translated_embeds = None
        await self.config.guild(ctx.guild).buttons.set([b.model_dump() for b in buttons])
        await ctx.send(_("Translations reset for all buttons."))

    @fluent.command()
    async def viewbuttons(self, ctx: commands.Context):
        """View all translation buttons"""
        buttons = await self.get_buttons(ctx.guild)
        if not buttons:
            return await ctx.send(_("There are no translation buttons at this time."))

        cached_messages: dict[int, discord.Message] = {}
        msg = ""
        for button in buttons:
            channel = ctx.guild.get_channel(button.channel_id)
            if not channel:
                continue
            if not isinstance(channel, discord.abc.Messageable):
                continue
            try:
                if button.message_id not in cached_messages:
                    message = await channel.fetch_message(button.message_id)
                    cached_messages[button.message_id] = message
                else:
                    message = cached_messages[button.message_id]
                msg += f"{message.jump_url} -> {button.target_lang} ({button.button_text})\n"
            except discord.NotFound:
                msg += f"Message not found <#{button.channel_id}> {button.message_id} -> {button.target_lang} ({button.button_text})\n"

        for p in pagify(msg, page_length=1000):
            await ctx.send(p)

    @fluent.command()
    @commands.is_owner()
    async def openai(self, ctx: commands.Context):
        """Set an openai key for translations"""
        tokens = await self.bot.get_shared_api_tokens("fluent_openai")
        message = _(
            "1. Go to [OpenAI](https://platform.openai.com/signup) and sign up for an account.\n"
            "2. Go to the [API keys](https://platform.openai.com/account/api-keys) page.\n"
            "3. Click the `+ Create new secret key` button to create a new API key.\n"
            "4. Copy the API key click the button below to set it."
        )
        await ctx.send(
            message,
            view=SetApiView(
                default_service="fluent_openai",
                default_keys={"key": tokens.get("key", "")},
            ),
        )

    @fluent.command()
    @commands.is_owner()
    async def deepl(self, ctx: commands.Context):
        """Set a deepl key for translations"""
        tokens = await self.bot.get_shared_api_tokens("fluent_deepl")
        message = _(
            "1. Go to [Deepl](https://www.deepl.com/pro#developer) and sign up for an account.\n"
            "2. Go to the [API keys](https://www.deepl.com/en/your-account/keys) page.\n"
            "3. Copy the API key click the button below to set it."
        )
        await ctx.send(
            message,
            view=SetApiView(
                default_service="fluent_deepl",
                default_keys={"key": tokens.get("key", "")},
            ),
        )

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
                discord.CategoryChannel,
            ]
        ] = None,
    ):
        """
        Add a channel and languages to translate between

        Tip: Language 1 is the first to be converted. For example, if you expect most of the conversation to be
        in english, then make english language 2 to use less api calls.

        You can also specify a category channel to translate all channels within it.
        """
        if not channel:
            channel = ctx.channel

        if language1.lower() == language2.lower():
            txt = _("You can't use the same language for both parameters. {} to {} is still {}...").format(
                language1, language1, language1
            )
            return await ctx.send(txt)

        translator = api.TranslateManager()
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

    @fluent.command()
    @commands.bot_has_permissions(embed_links=True)
    async def only(
        self,
        ctx: commands.Context,
        target_language: str,
        channel: t.Optional[
            t.Union[
                discord.TextChannel,
                discord.Thread,
                discord.ForumChannel,
                discord.CategoryChannel,
            ]
        ] = None,
    ):
        """
        Add a channel that translates all messages to a single language

        Unlike `[p]fluent add` which translates between two languages,
        this translates all messages to the specified target language
        regardless of the source language.

        You can also specify a category channel to translate all channels within it.
        """
        if not channel:
            channel = ctx.channel

        translator = api.TranslateManager()
        lang = await translator.get_lang(target_language)

        if not lang:
            txt = _("Target language is invalid.")
            return await ctx.send(txt)

        async with self.config.guild(ctx.guild).channels() as channels:
            cid = str(channel.id)
            if cid in channels.keys():
                txt = _("❌ {} is already a fluent channel.").format(channel.mention)
                return await ctx.send(txt)
            else:
                channels[cid] = {"target": target_language}
                txt = _("✅ Fluent channel has been set to translate all messages to {}!").format(target_language)
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
                discord.CategoryChannel,
            ]
        ] = None,
    ):
        """Remove a channel or category from Fluent"""
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
        """View all fluent channels and categories"""
        channels = await self.config.guild(ctx.guild).channels()
        msg = ""
        for cid, langs in channels.items():
            channel = ctx.guild.get_channel(int(cid))
            if not channel:
                continue
            # Determine channel type indicator
            if isinstance(channel, discord.CategoryChannel):
                channel_ref = f"📁 {channel.name}"
            else:
                channel_ref = channel.mention
            # Handle "only" mode (single target language)
            if "target" in langs:
                target = langs["target"]
                msg += f"{channel_ref} `(-> {target})`\n"
            else:
                l1 = langs["lang1"]
                l2 = langs["lang2"]
                msg += f"{channel_ref} `({l1} <-> {l2})`\n"

        if not msg:
            return await ctx.send(_("There are no fluent channels at this time."))
        final = _("**Fluent Settings**\n{}").format(msg.strip())
        for p in pagify(final, page_length=1000):
            await ctx.send(p)

    def _get_translatable_content(self, content: str) -> t.Optional[str]:
        """Extract translatable content from a message.

        Strips out non-translatable elements and returns the cleaned text,
        or None if there's nothing worth translating.

        Filters out:
        - URLs/links
        - Custom Discord emoji
        - Discord mentions (@user, #channel, @role)
        - Code blocks (```multiline``` and `inline`)
        - Messages with no alphabetic characters
        - Very short content (less than 2 letters)
        """
        text = content.strip()

        # Remove URLs
        text = constants.URL_PATTERN.sub("", text).strip()
        if not text:
            return None

        # Remove custom Discord emoji
        text = constants.CUSTOM_EMOJI_PATTERN.sub("", text).strip()
        if not text:
            return None

        # Remove Discord mentions (@user, #channel, @role)
        text = constants.DISCORD_MENTION_PATTERN.sub("", text).strip()
        if not text:
            return None

        # Remove code blocks (```code``` and `inline code`)
        text = constants.CODE_BLOCK_PATTERN.sub("", text).strip()
        if not text:
            return None

        # Check if remaining content is only numbers/punctuation/whitespace (no letters)
        if not any(c.isalpha() for c in text):
            return None

        # Check for very short content (less than 2 letters after filtering)
        alpha_chars = [c for c in text if c.isalpha()]
        if len(alpha_chars) < 2:
            return None

        return text

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

        # Get cleaned content (strips URLs, code blocks, mentions, emoji)
        clean_content = self._get_translatable_content(message.content)
        if not clean_content:
            return

        channels = await self.get_channels(message.guild)
        channel_id = str(message.channel.id)

        # Check if channel is directly configured, or if its parent category is configured
        channel_config = None
        if channel_id in channels:
            channel_config = channels[channel_id]
        else:
            category_id = getattr(message.channel, "category_id", None)
            if category_id is not None:
                category_id = str(category_id)
            else:
                category_id = None
            if category_id in channels:
                channel_config = channels[category_id]

        if channel_config is None:
            return

        channel = message.channel

        translator = api.TranslateManager()

        # Handle "only" mode - translate all messages to a single target language
        if "target" in channel_config:
            target_lang = channel_config["target"]
            log.debug(f"Translating to target language: {target_lang}")

            try:
                trans: api.Result = await self.translate(clean_content, target_lang, force=True)
            except Exception as e:
                log.error("Translation failed in 'only' mode", exc_info=e)
                setattr(self.bot, "_last_exception", e)
                return

            if trans is None:
                log.debug("Translation returned None")
                return

            # If translated text is the same as the source, no need to send
            if trans.text.lower() == clean_content.lower() or trans.src == trans.dest:
                log.debug("Translated text is the same as the source, no need to send")
                return

            if message.channel.permissions_for(message.guild.me).embed_links:
                embed = discord.Embed(description=trans.text, color=message.author.color)
                embed.set_footer(text=f"{trans.src} -> {trans.dest}")
                try:
                    await message.reply(embed=embed, mention_author=False)
                except (discord.NotFound, AttributeError):
                    await channel.send(embed=embed)
            else:
                try:
                    await message.reply(trans.text, mention_author=False)
                except (discord.NotFound, AttributeError):
                    await channel.send(trans.text)
            return

        # Handle bidirectional mode (lang1 <-> lang2)
        lang1 = channel_config["lang1"]
        lang2 = channel_config["lang2"]
        log.debug(f"Translating... {lang1} <-> {lang2}")

        async with channel.typing():
            # Attempts to translate message into language1.
            try:
                trans = await self.translate(clean_content, lang1, force=True)
            except Exception as e:
                log.error("Initial listener translation failed", exc_info=e)
                setattr(self.bot, "_last_exception", e)
                return

            if trans is None:
                log.debug("Auto translation first phase returned None")
                return

            source = await translator.get_lang(trans.src)
            source = source.split("-")[0].lower() if source else trans.src.lower()
            target = await translator.get_lang(lang1)
            target = target.split("-")[0].lower() if target else lang1.lower()
            log.debug(f"Source: {source}, target: {target}")
            log.debug(f"Raw Source: {trans.src}")

            # If the source language is also language1, translate into language2
            # If source language was language2, this saves api calls because translating gets the source and translation
            if source == target:
                try:
                    trans = await self.translate(clean_content, lang2)
                except Exception as e:
                    log.error("Secondary listener translation failed", exc_info=e)
                    return

                if trans is None:
                    return await channel.send(_("Unable to finish translation, perhaps the API is down."))

            # If translated text is the same as the source, no need to send
            if trans.text.lower() == clean_content.lower():
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
    async def on_assistant_cog_add(self, cog: AssistantRegistry):
        schema = {
            "name": "get_translation",
            "description": "Translate text into another language",
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
        await cog.register_function(cog_name="Fluent", schema=schema, category="utility")

    async def get_translation(self, message: str, to_language: str, *args, **kwargs) -> str:
        translator = api.TranslateManager()
        lang = await translator.get_lang(to_language)
        if not lang:
            return _("Invalid target language")
        try:
            translation = await self.translate(message, lang)
            return f"{translation.text}\n({translation.src} -> {lang})"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------ RPC
    # Localhost JSON-RPC surface (requires Red's --rpc flag, no-op otherwise).
    # Wire names are the method name uppercased: FLUENT__RPC_ADD_TRANSLATE_BUTTON etc.

    def _rpc_resolve(self, guild_id, channel_id, message_id) -> tuple:
        """-> (guild, channel, message_id, error_dict). Exactly one of guild/error is None."""
        try:
            guild_id, channel_id, message_id = int(guild_id), int(channel_id), int(message_id)
        except (TypeError, ValueError):
            return None, None, None, {"ok": False, "error": "ids must be integers"}
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return None, None, None, {"ok": False, "error": f"guild not found: {guild_id}"}
        channel = guild.get_channel_or_thread(channel_id)
        if channel is None or not isinstance(channel, discord.abc.Messageable):
            return None, None, None, {"ok": False, "error": f"channel not found: {channel_id}"}
        return guild, channel, message_id, None

    async def rpc_add_translate_button(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        target_lang: str,
        button_text: str,
    ) -> dict:
        """Add a translation button to any message. Same logic as [p]fluent addbutton."""
        try:
            guild, channel, message_id, err = self._rpc_resolve(guild_id, channel_id, message_id)
            if err:
                return err
            try:
                message = await channel.fetch_message(message_id)
            except discord.NotFound:
                return {"ok": False, "error": f"message not found: {message_id}"}

            status = await self.add_translate_button(
                guild, channel.id, message_id, str(target_lang), str(button_text)
            )
            if status == "invalid_lang":
                return {"ok": False, "error": f"invalid target language: {target_lang}"}

            buttons = await self.get_buttons(guild)
            langs = sorted(b.target_lang for b in buttons if b.message_id == message_id)
            res = {"ok": True, "jump_url": message.jump_url, "buttons": langs}
            if status == "exists":
                res["existing"] = True
            return res
        except Exception as e:
            log.error("rpc_add_translate_button failed", exc_info=e)
            return {"ok": False, "error": str(e)}

    async def rpc_remove_translate_button(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        target_lang: str,
    ) -> dict:
        """Remove a translation button from a message. Same logic as [p]fluent removebutton."""
        try:
            guild, channel, message_id, err = self._rpc_resolve(guild_id, channel_id, message_id)
            if err:
                return err

            status = await self.remove_translate_button(guild, channel.id, message_id, str(target_lang))
            if status == "not_found":
                return {"ok": False, "error": "no button found for that message/language"}

            buttons = await self.get_buttons(guild)
            langs = sorted(b.target_lang for b in buttons if b.message_id == message_id)
            return {"ok": True, "buttons": langs}
        except Exception as e:
            log.error("rpc_remove_translate_button failed", exc_info=e)
            return {"ok": False, "error": str(e)}

    async def rpc_list_translate_buttons(self, guild_id: int, message_id: int = None) -> dict:
        """List stored translation buttons, optionally filtered to one message."""
        try:
            try:
                guild_id = int(guild_id)
                message_id = int(message_id) if message_id is not None else None
            except (TypeError, ValueError):
                return {"ok": False, "error": "ids must be integers"}
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return {"ok": False, "error": f"guild not found: {guild_id}"}
            buttons = await self.get_buttons(guild)
            if message_id is not None:
                buttons = [b for b in buttons if b.message_id == message_id]
            buttons.sort(key=lambda x: (x.message_id, x.target_lang))
            return {"ok": True, "buttons": [b.model_dump() for b in buttons]}
        except Exception as e:
            log.error("rpc_list_translate_buttons failed", exc_info=e)
            return {"ok": False, "error": str(e)}
