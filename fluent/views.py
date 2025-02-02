import asyncio
import copy  # Add this import at the top
import logging
from typing import Callable, List

import discord
from redbot.core import Config
from redbot.core.bot import Red
from redbot.core.i18n import Translator

from .abc import MixinMeta
from .common.models import TranslateButton

log = logging.getLogger("red.vrt.fluent.views")
_ = Translator("Fluent", __file__)


class MenuButton(discord.ui.Button):
    def __init__(self, response_func: Callable, label: str, translate_button: TranslateButton):
        super().__init__(label=label)
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

        # After translations, before saving
        log.debug(f"Original embeds after translation: {translate_button.original_embeds}")
        log.debug(f"New translated embeds: {new_embeds}")

        await interaction.edit_original_response(
            content=translate_button.translated_content,
            embeds=translate_button.get_embeds(),
        )

        current_buttons = await self.cog.get_buttons(message.guild)
        if translate_button in current_buttons:
            current_buttons.remove(translate_button)
        current_buttons.append(translate_button)
        await self.config.guild(message.guild).buttons.set([b.model_dump() for b in current_buttons])
        log.info(f"Updated translation button {translate_button}")
