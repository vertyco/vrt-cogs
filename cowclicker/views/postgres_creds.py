from contextlib import suppress

import asyncpg
import discord
from redbot.core import commands

from ..abc import MixinMeta


class ConfigModal(discord.ui.Modal):
    def __init__(self, current: dict):
        self.data = None
        super().__init__(title="Set Postgres Info", timeout=240)
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
        if not self.port.value.isdigit():
            return await interaction.response.send_message("Port must be a number", ephemeral=True)
        if not self.host.value.replace(".", "").isdigit():
            return await interaction.response.send_message("Invalid IP address", ephemeral=True)
        elif not self.host.value.count(".") == 3:
            return await interaction.response.send_message("Invalid IP address", ephemeral=True)
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

        self.message: discord.Message = None

        self.data = None

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This isn't your menu!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            with suppress(discord.HTTPException):
                await self.message.delete()

    async def start(self):
        txt = "Configure your Postgres Connection info.\n\n-# Database name should be the maintenance database"
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

        async def _respond(txt: str):
            try:
                await interaction.edit_original_response(content=txt)
            except discord.HTTPException:
                try:
                    await interaction.followup.send(txt, ephemeral=True)
                except discord.HTTPException:
                    await interaction.channel.send(txt, delete_after=10)

        await interaction.edit_original_response(content="Testing connection...")
        try:
            conn = await asyncpg.connect(**modal.data, timeout=5)
        except asyncpg.InvalidPasswordError:
            return await _respond("Invalid password!")
        except asyncpg.InvalidCatalogNameError:
            return await _respond("Invalid database name!")
        except asyncpg.InvalidAuthorizationSpecificationError:
            return await _respond("Invalid user!")
        finally:
            await conn.close()

        await self.cog.bot.set_shared_api_tokens("postgres", **modal.data)
        await interaction.edit_original_response(content="Postgres connection info set", view=None)
        if self.cog.db:
            await self.cog.db.close_connection_pool()
        await self.cog.initalize()
