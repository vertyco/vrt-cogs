import logging
from contextlib import suppress

import discord

log = logging.getLogger("red.vrt.views.dynamic_modal")


class DynamicModal(discord.ui.Modal):
    def __init__(self, title: str, field_data: dict, timeout: int = 240):
        super().__init__(title=title, timeout=timeout)
        self.title = title

        self.inputs: dict | None = None
        self.fields: dict[str, discord.ui.TextInput] = {}
        for k, v in field_data.items():
            field = discord.ui.TextInput(
                label=v.get("label", "UNSET"),
                style=v.get("style", discord.TextStyle.short),
                placeholder=v.get("placeholder"),
                default=v.get("default"),
                required=v.get("required", True),
                min_length=v.get("min_length") if v.get("required") else None,
                max_length=v.get("max_length"),
            )
            self.add_item(field)
            self.fields[k] = field

    async def on_submit(self, interaction: discord.Interaction):
        self.inputs = {}
        for k, v in self.fields.items():
            self.inputs[k] = v.value
        with suppress(discord.NotFound):
            await interaction.response.defer()
        self.stop()

    async def on_timeout(self) -> None:
        self.stop()
        return await super().on_timeout()

    async def on_error(self, interaction: discord.Interaction, error: Exception, /) -> None:
        txt = (
            f"DynamicModal failed for {interaction.user.name}!\n"
            f"Guild: {interaction.guild}\n"
            f"Title: {self.title}\n"
        )
        log.error(txt, exc_info=error)
