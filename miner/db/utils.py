import typing as t

import discord
from aiocache import cached

from ..common import constants
from .tables import GlobalSettings, GuildSettings, Player


def key_builder(func: t.Callable, *args, **kwargs) -> str:
    func_name = str(func.__name__).replace("get_cached_", "miner_")
    target = args[1] if len(args) > 1 else None
    if target is None and kwargs:
        # Fallback for keyword-only invocation
        target = next(iter(kwargs.values()))
    if hasattr(target, "id"):
        target = target.id
    return f"{func_name}:{target}"


class DBUtils:
    @staticmethod
    async def get_create_global_settings() -> GlobalSettings:
        settings: GlobalSettings = await GlobalSettings.objects().get_or_create(
            (GlobalSettings.key == 1), defaults={GlobalSettings.key: 1}
        )
        return settings

    @staticmethod
    @cached(ttl=60)
    async def get_spawn_timing() -> tuple[int, int]:
        """Return the global min and max spawn intervals in seconds.

        Falls back to the defaults in constants if no values are set.
        Cached for a short period to avoid excessive database queries.
        """
        settings = await DBUtils.get_create_global_settings()
        min_interval = settings.min_spawn_interval or constants.MIN_TIME_BETWEEN_SPAWNS
        max_interval = settings.max_spawn_interval or constants.ABSOLUTE_MAX_TIME_BETWEEN_SPAWNS
        # Ensure min is never >= max; fall back to sane defaults if misconfigured.
        if min_interval >= max_interval:
            min_interval = constants.MIN_TIME_BETWEEN_SPAWNS
            max_interval = constants.ABSOLUTE_MAX_TIME_BETWEEN_SPAWNS
        return min_interval, max_interval

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

    # Cached roughly for the longest possible rock lifetime
    @cached(ttl=constants.MAX_ROCK_TTL_SECONDS, key_builder=key_builder)
    async def get_cached_player_tool(self, user: int) -> constants.ToolName:
        player = await self.get_create_player(user)
        tool: constants.ToolName = player.tool
        return tool

    @cached(ttl=10, key_builder=key_builder)
    async def get_cached_guild_settings(self, guild: int) -> GuildSettings:
        settings = await self.get_create_guild_settings(guild)
        return settings
