import discord
from aiocache import cached

from ..common import constants
from .tables import GlobalSettings, GuildSettings, Player


class DBUtils:
    @staticmethod
    async def get_create_global_settings() -> GlobalSettings:
        settings: GlobalSettings = await GlobalSettings.objects().get_or_create(
            (GlobalSettings.key == 1), defaults={GlobalSettings.key: 1}
        )
        return settings

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

    @cached(ttl=constants.ROCK_TTL_SECONDS, key="miner_player_tool:{user}")  # Cached for length of time that rocks last
    async def get_cached_player_tool(self, user: int) -> constants.ToolName:
        player = await self.get_create_player(user)
        tool: constants.ToolName = player.tool
        return tool

    @cached(ttl=10, key="miner_guild_settings:{guild}")
    async def get_cached_guild_settings(self, guild: int) -> GuildSettings:
        settings = await self.get_create_guild_settings(guild)
        return settings
