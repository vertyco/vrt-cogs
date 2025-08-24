import discord

from .tables import GuildSettings, Player


class DBUtils:
    @staticmethod
    async def get_create_player(user: discord.User | discord.Member | int) -> Player:
        uid = user if isinstance(user, int) else user.id
        player = await Player.objects().get_or_create((Player.id == uid), defaults={Player.id: uid})
        return player

    @staticmethod
    async def get_create_guild_settings(guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        settings = await GuildSettings.objects().get_or_create(
            (GuildSettings.id == gid), defaults={GuildSettings.id: gid}
        )
        return settings
