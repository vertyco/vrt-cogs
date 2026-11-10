import asyncio
import copy
import logging
from typing import Callable, Collection, List

import discord
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .common.models import TranslateButton

log = logging.getLogger("red.vrt.fluent.views")
_ = Translator("Fluent", __file__)

ID_PREFIX = "fluent:"
# Discord's cap on all the text in one Components V2 message
TEXT_LIMIT = 4000


def is_translate_row(item: discord.ui.Item, labels: Collection[str]) -> bool:
    """Whether a row holds only this cog's translate buttons.

    The buttons carry a fixed id. A row whose buttons still have random ids is recognised by its labels.
    """
    if not isinstance(item, discord.ui.ActionRow) or not item.children:
        return False
    return all(
        isinstance(child, discord.ui.Button)
        and child.custom_id is not None
        and (child.custom_id.startswith(ID_PREFIX) or child.label in labels)
        for child in item.children
    )


def reuse_uploads(layout: discord.ui.LayoutView, channel_id: int) -> None:
    """Point pictures and files back at the message's own uploads.

    A fetched message gives each upload as a CDN link. Sending that link back in an edit would
    swap the upload for an external picture, so it goes back as attachment://<filename>.
    """
    prefix = f"https://cdn.discordapp.com/attachments/{channel_id}/"
    for item in layout.walk_children():
        holders = item.items if isinstance(item, discord.ui.MediaGallery) else [item]
        for holder in holders:
            if not isinstance(holder, (discord.ui.Thumbnail, discord.ui.File, discord.MediaGalleryItem)):
                continue
            if holder.media.url.startswith(prefix):
                holder.media = "attachment://" + holder.media.url.split("?")[0].rsplit("/", 1)[-1]


def fit_texts(texts: List[str]) -> List[str]:
    """Trim texts so together they fit Discord's limit, leaving each one at least a character."""
    room = TEXT_LIMIT - len(texts)
    fitted = []
    for text in texts:
        text = text[: room + 1]
        room -= len(text) - 1
        fitted.append(text)
    return fitted


class MenuButton(discord.ui.Button):
    def __init__(self, response_func: Callable, label: str, translate_button: TranslateButton):
        # A fixed id lets the button keep working after a restart without editing its message
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"{ID_PREFIX}{translate_button.message_id}:{translate_button.target_lang}",
        )
        self.func = response_func
        self.translate_button = translate_button

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.func(interaction, self.translate_button)


class TranslateMenu(discord.ui.View):
    def __init__(self, cog: MixinMeta, buttons: List[TranslateButton]):
        super().__init__(timeout=None)
        self.cog = cog
        self.bot: Red = cog.bot
        self.config: Config = cog.config
        self.buttons = buttons

        for button in buttons:
            self.add_item(MenuButton(self.translate, button.button_text, button))

    async def translate(self, interaction: discord.Interaction, translate_button: TranslateButton):
        if not interaction.message:
            return await interaction.followup.send(_("Message not found!"), ephemeral=True)

        self.buttons = await self.cog.get_buttons(interaction.guild)
        if translate_button not in self.buttons:
            return await interaction.followup.send(_("This button is no longer valid!"), ephemeral=True)

        translate_button = self.buttons[self.buttons.index(translate_button)]

        message: discord.Message = interaction.message
        if message.flags.components_v2:
            return await self.translate_layout(interaction, message, translate_button)

        if translate_button.up_to_date(message) and (
            translate_button.translated_content or translate_button.translated_embeds
        ):
            return await interaction.edit_original_response(
                content=translate_button.translated_content,
                embeds=translate_button.get_embeds(),
            )

        if not (translate_button.original_content or translate_button.original_embeds):
            log.info(f"Translating {message.id} to {translate_button.target_lang} for the first time")
        else:
            log.debug(f"Re-translating {message.id} to {translate_button.target_lang}")

        # Store original content before any translations
        translate_button.original_content = message.content
        embed_copy: list[dict] = copy.deepcopy([embed.to_dict() for embed in message.embeds])
        translate_button.original_embeds = embed_copy

        # Create deep copies for translation to avoid modifying originals
        working_embeds = [embed.copy() for embed in message.embeds]

        # Gather all translatable content
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

        # Translate all content concurrently
        if to_translate:
            tasks_dict = {
                key: self.cog.translate(text, translate_button.target_lang, True) for key, text in to_translate
            }
            results = await asyncio.gather(*tasks_dict.values())
            translation_map = dict(zip(tasks_dict.keys(), results))
        else:
            translation_map = {}

        # Update content
        if message.content:
            content = translation_map.get("content")
            translate_button.translated_content = (content.text if content else message.content)[:2000]
        else:
            translate_button.translated_content = None

        # Update embeds
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
                fieldname: str = name_translation.text if name_translation else field.name
                value: str = value_translation.text if value_translation else field.value
                new_embed.add_field(
                    name=fieldname[:256],
                    value=value[:1024],
                    inline=field.inline,
                )
            new_embeds.append(new_embed.to_dict())

        translate_button.translated_embeds = new_embeds

        await interaction.edit_original_response(
            content=translate_button.translated_content,
            embeds=translate_button.get_embeds(),
        )

        await self.save(message.guild, translate_button)

    async def translate_layout(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
        translate_button: TranslateButton,
    ):
        """Reply with a copy of a Components V2 message whose text blocks are translated."""
        layout = discord.ui.LayoutView.from_message(message)
        labels = {b.button_text for b in self.buttons if b.message_id == message.id}
        for item in list(layout.walk_children()):
            # The copy leaves out the translate buttons (their ids only work on the real message)
            # and file blocks (a file can only point at an upload of its own message).
            if is_translate_row(item, labels) or isinstance(item, discord.ui.File):
                (item.parent or layout).remove_item(item)

        displays = [item for item in layout.walk_children() if isinstance(item, discord.ui.TextDisplay)]
        originals = [display.content for display in displays]
        if not originals:
            return await interaction.edit_original_response(content=_("❌ No content to translate."))

        if translate_button.original_texts != originals or not translate_button.translated_texts:
            log.info(f"Translating {message.id} to {translate_button.target_lang}")
            results = await asyncio.gather(
                *(self.cog.translate(text, translate_button.target_lang, True) for text in originals)
            )
            translate_button.original_texts = originals
            translate_button.translated_texts = [
                res.text if res and res.text else text for res, text in zip(results, originals)
            ]
            # A failed translation is shown untranslated but not kept, so the next click tries again
            if all(results):
                await self.save(message.guild, translate_button)

        for display, text in zip(displays, fit_texts(translate_button.translated_texts)):
            display.content = text
        await interaction.edit_original_response(view=layout)

    async def save(self, guild: discord.Guild, translate_button: TranslateButton):
        current_buttons = await self.cog.get_buttons(guild)
        if translate_button in current_buttons:
            current_buttons.remove(translate_button)
        current_buttons.append(translate_button)
        await self.config.guild(guild).buttons.set([b.model_dump() for b in current_buttons])
        log.info(f"Updated translation button {translate_button}")
