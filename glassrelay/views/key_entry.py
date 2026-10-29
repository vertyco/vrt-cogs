import logging
import typing as t

import discord
from discord import ui
from redbot.core import commands

log = logging.getLogger("red.vrt.glassrelay.views.key_entry")


class KeyModal(ui.Modal):
    """The form the key is pasted into"""

    def __init__(self, entry: "KeyEntry"):
        super().__init__(title="GlassRelay API key")
        self.entry = entry
        self.key = ui.TextInput(placeholder="Paste the key from your GlassRelay dashboard")
        self.add_item(ui.Label(text="API key", component=self.key))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.entry.submitted(interaction, self.key.value.strip())


class KeyEntry(ui.LayoutView):
    """Steps plus a button that opens a form for the API key, so the key never shows in the channel.

    on_key checks and saves the key. It returns whether that worked and the text to show.
    """

    def __init__(
        self,
        ctx: commands.Context,
        steps: str,
        on_key: t.Callable[[str], t.Awaitable[tuple[bool, str]]],
    ):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.steps = steps
        self.on_key = on_key
        self.message: discord.Message | None = None
        # Why the last key failed, kept on screen when the menu times out
        self.error: str | None = None
        self.button = ui.Button(label="Enter API key", style=discord.ButtonStyle.primary)
        self.button.callback = self.open_form
        self.show(steps, with_button=True)

    def show(self, text: str, with_button: bool) -> None:
        self.clear_items()
        container = ui.Container(ui.TextDisplay(f"### Connect your GlassRelay store\n{text}"))
        if with_button:
            container.add_item(ui.ActionRow(self.button))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        text = "This menu timed out. Run the command again."
        if self.error:
            text = f"{self.error}\n\n{text}"
        self.show(text, with_button=False)
        try:
            await self.message.edit(view=self)
        except discord.HTTPException as e:
            log.warning("Couldn't edit the timed out key menu", exc_info=e)

    async def open_form(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(KeyModal(self))

    async def submitted(self, interaction: discord.Interaction, api_key: str) -> None:
        self.show("Checking the key...", with_button=False)
        await interaction.response.edit_message(view=self)
        try:
            done, text = await self.on_key(api_key)
        except Exception as e:
            log.error(f"Checking a GlassRelay key failed in {self.ctx.guild}", exc_info=e)
            done, text = False, "Something went wrong. The bot owner can find the error in the bot's logs."
        if done:
            self.stop()
            self.show(text, with_button=False)
        else:
            # Keep the button so they can try another key
            self.error = text
            self.show(f"{text}\n\n{self.steps}", with_button=True)
        await interaction.edit_original_response(view=self)
