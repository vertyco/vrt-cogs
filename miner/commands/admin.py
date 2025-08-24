import typing as t

import discord
from redbot.core import commands

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import ActiveChannel, GuildSettings, ensure_db_connection
from ..views.mining_view import RockView


class Admin(MixinMeta):
    @commands.group(name="minerset")
    @commands.admin_or_permissions(manage_guild=True)
    async def miner_set(self, ctx: commands.Context):
        """Admin commands"""

    @miner_set.command(name="toggle")
    @ensure_db_connection()
    async def miner_toggle(self, ctx: commands.Context, *, channel: t.Optional[discord.TextChannel]):
        """Toggle active mining channels"""
        if not channel:
            channel = ctx.channel

        await GuildSettings.objects().get_or_create(
            GuildSettings.id == ctx.guild.id, defaults={GuildSettings.id: ctx.guild.id}
        )
        existing = await ActiveChannel.objects().get(ActiveChannel.id == channel.id)
        if existing:
            await ActiveChannel.delete().where(ActiveChannel.id == channel.id)
            await ctx.send(f"Mining in {channel.mention} has been disabled.")
        else:
            await ActiveChannel.insert(ActiveChannel(id=channel.id, guild=ctx.guild.id))
            await ctx.send(f"Mining in {channel.mention} has been enabled.")

    @miner_set.command(name="view")
    @ensure_db_connection()
    async def miner_view(self, ctx: commands.Context):
        """View active mining channels"""
        active_channels = (
            await ActiveChannel.select(ActiveChannel.id).where(ActiveChannel.guild == ctx.guild.id).output(as_list=True)
        )
        invalid_channels = [i for i in active_channels if not ctx.guild.get_channel(i)]
        if invalid_channels:
            await ctx.send("Some channels are no longer valid, removing them from the list.")
            await ActiveChannel.delete().where(ActiveChannel.id.is_in(invalid_channels))
            active_channels = [i for i in active_channels if i not in invalid_channels]

        if not active_channels:
            await ctx.send("There are no active mining channels.")
            return

        await ctx.send(
            f"Active mining channels: {', '.join(ctx.guild.get_channel(i).mention for i in active_channels)}"
        )

    @miner_set.command(name="spawn")
    @ensure_db_connection()
    async def miner_spawn(
        self,
        ctx: commands.Context,
        channel: t.Optional[discord.TextChannel],
        *,
        rock_type: constants.RockTierName,
    ):
        """Spawn a new mining rock in the specified channel."""
        if not channel:
            channel = ctx.channel

        await GuildSettings.objects().get_or_create(
            GuildSettings.id == ctx.guild.id, defaults={GuildSettings.id: ctx.guild.id}
        )
        rock = constants.ROCK_TYPES[rock_type]
        view = RockView(self, rock)
        await view.start(channel)
