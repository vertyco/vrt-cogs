import discord

from ..db.tables import GuildSettings


class DBUtils:
    async def get_create_guild(self, guild: discord.Guild | int) -> GuildSettings:
        guild_id = guild.id if isinstance(guild, discord.Guild) else guild
        settings = await GuildSettings.objects().get_or_create(
            where=(GuildSettings.id == guild_id), defaults={GuildSettings.id: guild_id}
        )
        return settings
