import asyncio
import logging

import discord
from redbot.core import commands
from sentry_sdk import add_breadcrumb

from ..abc import MixinMeta

log = logging.getLogger("red.vrt.profiler.listeners")


class Listeners(MixinMeta):
    # ------------------- LISTENERS ------------------- #
    @commands.Cog.listener()
    async def on_cog_add(self, cog: commands.Cog) -> None:
        await asyncio.to_thread(self.map_methods)
        if cog.qualified_name in self.db.tracked_cogs:
            await asyncio.to_thread(self.attach_cog, cog.qualified_name)

    @commands.Cog.listener()
    async def on_cog_remove(self, cog: commands.Cog) -> None:
        await asyncio.to_thread(self.map_methods)
        self.detach_cog(cog.qualified_name)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: dict[str, str]):
        if service_name != "sentry":
            return
        await self.start_sentry(await self.get_dsn(api_tokens))

    # ------------------- BREADCRUMBS ------------------- #
    @staticmethod
    def get_ctx_crumbs(ctx: commands.Context) -> dict[str, str]:
        data = {
            "command_name": getattr(ctx.command, "qualified_name", "None"),
            "cog_name": getattr(ctx.command.cog, "qualified_name", "None"),
            "author_id": getattr(ctx.author, "id", "None"),
            "guild_id": getattr(ctx.guild, "id", "None"),
            "channel_id": getattr(ctx.channel, "id", "None"),
        }
        for comm_arg, value in ctx.kwargs.items():
            data[f"command_arg_{comm_arg}"] = value
        return data

    @staticmethod
    def get_interaction_crumbs(interaction: discord.Interaction) -> dict[str, str]:
        data = {
            "interaction_id": getattr(interaction, "id", "None"),
            "channel_id": getattr(interaction.channel, "id", "None"),
            "guild_id": getattr(interaction.guild, "id", "None"),
            "user_id": getattr(interaction.user, "id", "None"),
            "message_id": getattr(interaction.message, "id", "None"),
        }
        return data

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        data = self.get_ctx_crumbs(ctx)
        add_breadcrumb(
            type="user",
            category="on_command",
            level="info",
            message=f"Command '{data['command_name']}' invoked by {ctx.author.name} ({ctx.author.id})",
            data=data,
        )

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        data = self.get_ctx_crumbs(ctx)
        add_breadcrumb(
            type="user",
            category="on_command_completion",
            level="info",
            message=f"Command '{data['command_name']}' completed for {ctx.author.name} ({ctx.author.id})",
            data=data,
        )

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        if not ctx.command:
            return
        data = self.get_ctx_crumbs(ctx)
        add_breadcrumb(
            type="user",
            category="on_command_error",
            level="error",
            message=f"Command '{data['command_name']}' raised an error for {ctx.author.name} ({ctx.author.id}): {error}",
            data=data,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        data = self.get_interaction_crumbs(interaction)
        add_breadcrumb(
            type="user",
            category="on_interaction",
            level="info",
            message=f"Interaction '{interaction.type.name}' invoked by {interaction.user.name} ({interaction.user.id})",
            data=data,
        )
