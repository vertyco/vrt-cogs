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
        await interaction.response.defer(ephemeral=True)
        await self.func(interaction, self.translate_button)


class TranslateMenu(discord.ui.View):
    def __init__(self, cog: MixinMeta, buttons: List[TranslateButton]):
        super().__init__(timeout=600)
        self.cog = cog
        self.bot: Red = cog.bot
        self.config: Config = cog.config
        self.buttons = buttons

        for button in buttons:
            self.add_item(MenuButton(self.translate, button.button_text, button))

    async def translate(self, interaction: discord.Interaction, translate_button: TranslateButton):
        if not interaction.message:
            return await interaction.followup.send(_("Message not found!"), ephemeral=True)
        message: discord.Message = interaction.message
        if translate_button.up_to_date(message) and (
            translate_button.translated_content or translate_button.translated_embeds
        ):
            # No need to re-translate
            return await interaction.followup.send(
                content=translate_button.translated_content,
                embeds=translate_button.get_embeds(),
                ephemeral=True,
            )

        if message.content:
            content = await self.cog.translate(message.content, translate_button.target_lang)
            translate_button.translated_content = content.text if content else message.content
        else:
            translate_button.translated_content = None
        new_embeds = []
        for embed in message.embeds:
            new_embed = embed.copy()
            if new_embed.title:
                title = await self.cog.translate(new_embed.title, translate_button.target_lang)
                new_embed.title = title.text if title else new_embed.title
            if new_embed.description:
                description = await self.cog.translate(new_embed.description, translate_button.target_lang)
                new_embed.description = description.text if description else new_embed.description
            if new_embed.footer and new_embed.footer.text:
                footer = await self.cog.translate(new_embed.footer.text, translate_button.target_lang)
                new_embed.set_footer(
                    text=footer.text if footer else new_embed.footer.text,
                    icon_url=new_embed.footer.icon_url,
                )

            fields = new_embed.fields.copy()
            new_embed.clear_fields()
            for field in fields:
                name = await self.cog.translate(field.name, translate_button.target_lang)
                value = await self.cog.translate(field.value, translate_button.target_lang)
                new_embed.add_field(
                    name=name.text if name else field.name,
                    value=value.text if value else field.value,
                    inline=field.inline,
                )
            new_embeds.append(new_embed.to_dict())
        translate_button.translated_embeds = new_embeds

        await interaction.followup.send(
            content=translate_button.translated_content,
            embeds=translate_button.get_embeds(),
            ephemeral=True,
        )

        current_buttons = await self.cog.get_buttons(message.guild)
        if translate_button in current_buttons:
            current_buttons.remove(translate_button)
        current_buttons.append(translate_button)
        await self.config.guild(message.guild).buttons.set([b.model_dump() for b in current_buttons])
        log.info(f"Updated translation button {translate_button}")
