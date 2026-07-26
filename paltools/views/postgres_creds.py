import asyncio
import logging
from contextlib import suppress

import asyncpg
import discord
from redbot.core import commands
from redbot.core.i18n import Translator

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.paltools.views.postgres_creds")
_ = Translator("PalTools", __file__)


class ConfigModal(discord.ui.Modal):
    def __init__(self, current: dict):
        self.data = None
        super().__init__(title=_("Set Postgres Info"), timeout=240)
        self.host = discord.ui.TextInput(
            label="POSTGRES HOST",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("host"),
        )
        self.add_item(self.host)
        self.port = discord.ui.TextInput(
            label="POSTGRES PORT",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("port"),
        )
        self.add_item(self.port)
        self.user = discord.ui.TextInput(
            label="POSTGRES USER",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("user"),
        )
        self.add_item(self.user)
        self.password = discord.ui.TextInput(
            label="POSTGRES PASSWORD",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("password"),
        )
        self.add_item(self.password)
        self.database = discord.ui.TextInput(
            label="POSTGRES MAINTENANCE DATABASE",
            style=discord.TextStyle.short,
            required=True,
            default=current.get("database", "postgres"),
        )
        self.add_item(self.database)

    async def on_submit(self, interaction: discord.Interaction):
        # isdecimal, not isdigit: isdigit accepts superscripts that int() (inside asyncpg) rejects
        if not self.port.value.isdecimal() or not 1 <= int(self.port.value) <= 65535:
            # Stop as well, otherwise the caller's modal.wait() blocks until the 240s timeout
            self.stop()
            return await interaction.response.send_message(_("Port must be a number from 1 to 65535"), ephemeral=True)
        await interaction.response.defer()
        self.data = {
            "host": self.host.value,
            "port": self.port.value,
            "user": self.user.value,
            "password": self.password.value,
            "database": self.database.value,
        }
        self.stop()


class SetConnectionView(discord.ui.View):
    def __init__(self, cog: MixinMeta, ctx: commands.Context):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx

        self.message: discord.Message | None = None

        self.data = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(_("This isn't your menu!"), ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            with suppress(discord.HTTPException):
                await self.message.delete()

    async def start(self):
        txt = _("Configure your Postgres Connection info.\n\n-# Database name should be the maintenance database")
        self.message = await self.ctx.send(txt, view=self)

    @discord.ui.button(label="Configure", style=discord.ButtonStyle.primary)
    async def configure(self, interaction: discord.Interaction, buttons: discord.ui.Button):
        current = await self.cog.bot.get_shared_api_tokens("postgres")
        modal = ConfigModal(self.data or current)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if not modal.data:
            return
        self.data = modal.data

        async def respond(txt: str, done: bool = False):
            # The message itself, not the interaction: this button spent its response on
            # send_modal, and a modal leaves no original response to edit
            try:
                if self.message:
                    self.message = await self.message.edit(content=txt, view=None if done else self)
                    return
            except discord.HTTPException as e:
                log.debug("Could not edit the setup message: %s", e)
            try:
                await interaction.followup.send(txt, ephemeral=True)
            except discord.HTTPException as e:
                log.warning("Could not reply to the postgres setup interaction", exc_info=e)
                await interaction.channel.send(txt, delete_after=10)

        await respond(_("Testing connection..."))
        conn = None
        try:
            conn = await asyncpg.connect(**modal.data, timeout=5)
        except asyncpg.InvalidPasswordError:
            return await respond(_("Invalid password!"))
        except asyncpg.InvalidCatalogNameError:
            return await respond(_("Invalid database name!"))
        except asyncpg.InvalidAuthorizationSpecificationError:
            return await respond(_("Invalid user!"))
        except (OSError, asyncio.TimeoutError, asyncpg.PostgresError) as e:
            log.error("Postgres connection test failed", exc_info=e)
            return await respond(_("Connection failed: {}").format(e))
        finally:
            if conn:
                await conn.close()

        await self.cog.bot.set_shared_api_tokens("postgres", **modal.data)
        await respond(_("Postgres connection info set"), done=True)
        # Stop the view, otherwise on_timeout deletes this confirmation five minutes later, and
        # the plaintext credentials sit in self.data until then
        self.data = None
        self.stop()
