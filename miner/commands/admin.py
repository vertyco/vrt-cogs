import typing as t

import discord
from redbot.core import bank, commands

from ..abc import MixinMeta
from ..common import constants
from ..db.tables import ActiveChannel, GuildSettings, Player, ensure_db_connection
from ..views.mining_view import RockView


class Admin(MixinMeta):
    @commands.command(name="tempadd")
    async def miner_temp_add(self, ctx: commands.Context, role: discord.Role):
        async with ctx.typing():
            players = await Player.select(Player.id).output(as_list=True)
            added = 0
            for p in players:
                member = ctx.guild.get_member(p)
                if member and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Miner tempadd command")
                        added += 1
                    except discord.Forbidden:
                        await ctx.send(f"Failed to add role to {member.mention}, missing permissions.")
                    except discord.HTTPException:
                        await ctx.send(f"Failed to add role to {member.mention}, unknown error.")

            await ctx.send(f"Added role to {added} members.")

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

        embed = discord.Embed(title="Miner Settings", color=await self.bot.get_embed_color(ctx.channel))
        embed.add_field(name="Active Mining Channels", value=" ".join(f"<#{i}>" for i in active_channels) or "None")

        if await bank.is_global():
            settings = await self.db_utils.get_create_global_settings()
            field = "Only bot owner can change these settings\n"
        else:
            settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)
            field = ""
        creditsname = await bank.get_currency_name(ctx.guild)

        def _ratio_text(rate: float, resource: str) -> str:
            if rate >= 1:
                return f"`{int(rate)} {resource}` = `1 {creditsname}`"
            else:
                return f"`1 {resource}` = `{round(1 / rate)} {creditsname}`"

        field += f"Conversion: `{'Enabled' if settings.conversion_enabled else 'Disabled'}`\n"
        field += f"Stone: `{settings.stone_convert_rate}` ({_ratio_text(settings.stone_convert_rate, 'stone')})\n"
        field += f"Iron: `{settings.iron_convert_rate}` ({_ratio_text(settings.iron_convert_rate, 'iron')})\n"
        field += f"Gems: `{settings.gems_convert_rate}` ({_ratio_text(settings.gems_convert_rate, 'gems')})\n"
        embed.add_field(name="Resource Conversion Settings", value=field, inline=False)

        await ctx.send(embed=embed)

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

    @miner_set.command(name="toggleconvert")
    @ensure_db_connection()
    async def miner_remove_rock(self, ctx: commands.Context):
        """Toggle resource conversion on/off."""
        if await bank.is_global():
            if ctx.author.id not in self.bot.owner_ids:
                return await ctx.send(
                    "Only bot owners can toggle the global conversion setting when the bank system is global."
                )
            settings = await self.db_utils.get_create_global_settings()
        else:
            settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)

        settings.conversion_enabled = not settings.conversion_enabled
        await settings.save()

        status = "enabled" if settings.conversion_enabled else "disabled"
        await ctx.send(f"Resource conversion has been {status}.")

    @miner_set.command(name="convertratio")
    @ensure_db_connection()
    async def miner_convert_ratio(self, ctx: commands.Context, resource: constants.Resource, ratio: float):
        """View the conversion ratio for a resource.

        **Examples:**
        - `[p]minerset convertratio stone 20` (20 stone = 1 credit)
        - `[p]minerset convertratio iron 5` (5 iron = 1 credit)
        - `[p]minerset convertratio gems 0.1` (1 gem = 10 credits)

        """
        if ratio <= 0:
            await ctx.send("Ratio must be greater than 0.")
            return

        if await bank.is_global():
            if ctx.author.id not in self.bot.owner_ids:
                return await ctx.send(
                    "Only bot owners can set the global conversion ratio when the bank system is global."
                )
            settings = await self.db_utils.get_create_global_settings()
        else:
            settings = await self.db_utils.get_create_guild_settings(ctx.guild.id)

        setattr(settings, f"{resource}_convert_rate", ratio)

        await settings.save()

        creditsname = await bank.get_currency_name(ctx.guild)

        if ratio >= 1:
            ratio_text = f"`{ratio} {resource}` = `1 {creditsname}`"
        else:
            ratio_text = f"`1 {resource}` = `{round(1 / ratio)} {creditsname}`"

        await ctx.send(f"Set the conversion ratio for {resource} to {ratio}. {ratio_text}")
