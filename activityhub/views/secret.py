import asyncio
import logging

import aiohttp
import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta
from ..common.discord_api import DISCORD_TIMEOUT, secret_works

log = logging.getLogger("red.vrt.activityhub.views")
_ = Translator("ActivityHub", __file__)


class SecretModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title=_("Activities client secret"), timeout=240)
        self.secret = None
        self.field = discord.ui.TextInput(
            label=_("Client secret"),
            placeholder=_("Developer Portal > your bot > OAuth2"),
            style=discord.TextStyle.short,
            required=True,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.secret = self.field.value.strip()
        self.stop()


class SetSecretView(discord.ui.View):
    """Owner-only button that opens a form, checks the secret with Discord, then saves it to Red's shared API keys"""

    def __init__(self, cog: MixinMeta, ctx: commands.Context):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        try:
            await self.message.delete()
        except discord.HTTPException as e:
            log.debug("Couldn't delete the client secret prompt: %s", e)

    async def start(self):
        self.message = await self.ctx.send(
            _("Set the client secret that logs players in to your Activities."), view=self
        )

    async def check_with_discord(self, secret: str) -> bool | None:
        """True or False from Discord, or None when Discord couldn't be reached"""
        try:
            async with aiohttp.ClientSession(timeout=DISCORD_TIMEOUT) as http:
                return await secret_works(http, str(self.cog.bot.application_id), secret)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.error("Couldn't reach Discord to check the client secret", exc_info=e)
            return None

    @discord.ui.button(label=_("Set secret"), style=discord.ButtonStyle.primary)
    async def set_secret(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SecretModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.secret:
            return
        await self.message.edit(content=_("Checking the secret with Discord..."))
        valid = await self.check_with_discord(modal.secret)
        if valid is None:
            await self.message.edit(content=_("Couldn't reach Discord. Try again in a moment."))
            return
        if not valid:
            await self.message.edit(
                content=_("Discord rejected that secret. Copy it again from this bot's OAuth2 page.")
            )
            return
        await self.cog.bot.set_shared_api_tokens("activityhub", client_secret=modal.secret)
        await self.message.edit(content=_("Client secret saved."), view=None)
        self.stop()
