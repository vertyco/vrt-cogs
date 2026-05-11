import typing as t

import discord
from aiocache import cached
from piccolo.query.functions.aggregate import Sum

from ..common import constants
from .tables import (
    GlobalSettings,
    GuildSettings,
    Player,
    PlayerAchievement,
    PlayerAchievementStats,
    ResourceLedger,
)


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
    async def get_create_player(user: discord.User | discord.Member | int) -> Player:
        uid = user if isinstance(user, int) else user.id
        player = await Player.objects().get_or_create((Player.id == uid), defaults={Player.id: uid})
        return player

    @staticmethod
    async def get_create_player_achievement_stats(
        user: discord.User | discord.Member | int,
    ) -> PlayerAchievementStats:
        uid = user if isinstance(user, int) else user.id
        stats = await PlayerAchievementStats.objects().get_or_create(
            (PlayerAchievementStats.player == uid),
            defaults={PlayerAchievementStats.player: uid},
        )
        return stats

    @staticmethod
    async def get_player_achievements(user: discord.User | discord.Member | int) -> list[PlayerAchievement]:
        uid = user if isinstance(user, int) else user.id
        rows = await PlayerAchievement.objects().where(PlayerAchievement.player == uid)
        rows.sort(key=lambda row: row.created_on.timestamp() if row.created_on else 0.0, reverse=True)
        return rows

    @staticmethod
    async def ensure_player_achievements(
        user: discord.User | discord.Member | int,
        keys: t.Iterable[str],
    ) -> list[PlayerAchievement]:
        uid = user if isinstance(user, int) else user.id
        unique_keys = tuple(dict.fromkeys(key for key in keys if key))
        if not unique_keys:
            return []

        lookup_keys = [f"{uid}:{key}" for key in unique_keys]
        existing = await PlayerAchievement.objects().where(PlayerAchievement.lookup_key.is_in(lookup_keys))
        existing_lookup = {row.lookup_key for row in existing}

        created: list[PlayerAchievement] = []
        for key in unique_keys:
            lookup_key = f"{uid}:{key}"
            if lookup_key in existing_lookup:
                continue
            row = await PlayerAchievement.objects().get_or_create(
                (PlayerAchievement.lookup_key == lookup_key),
                defaults={
                    PlayerAchievement.lookup_key: lookup_key,
                    PlayerAchievement.player: uid,
                    PlayerAchievement.key: key,
                },
            )
            created.append(row)

        created.sort(key=lambda row: row.created_on.timestamp() if row.created_on else 0.0, reverse=True)
        return created

    @staticmethod
    async def get_player_resource_lower_bounds(
        user: discord.User | discord.Member | int,
    ) -> dict[constants.Resource, int]:
        uid = user if isinstance(user, int) else user.id
        bounds: dict[constants.Resource, int] = {resource: 0 for resource in constants.RESOURCES}

        query = ResourceLedger.select(ResourceLedger.resource, Sum(ResourceLedger.amount).as_alias("total")).where(
            (ResourceLedger.player == uid) & (ResourceLedger.amount > 0)
        )
        query = query.group_by(ResourceLedger.resource)
        rows: list[dict[str, t.Any]] = await query
        for row in rows:
            resource = t.cast(constants.Resource, row["resource"])
            bounds[resource] = int(row.get("total", 0) or 0)

        return bounds

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
