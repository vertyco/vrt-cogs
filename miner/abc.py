import asyncio
import typing as t
from abc import ABC, ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from piccolo.engine.postgres import PostgresEngine
from redbot.core.bot import Red

from .common import achievements, constants, tracker
from .db.tables import GuildSettings, PlayerAchievement, PlayerAchievementStats
from .db.utils import DBUtils


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: PostgresEngine | None
        self.db_utils: DBUtils

        self.chat_cache: tracker.ChannelChatCache
        self.guild_spawn_cooldowns: dict[int, float]
        self.guild_spawn_locks: dict[int, asyncio.Lock]

    @abstractmethod
    async def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def db_active(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def reset_durability_warnings(self, player_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def register_durability_ratio(self, player_id: int, ratio: float | None) -> float | None:
        raise NotImplementedError

    @abstractmethod
    def get_spawn_activity_metrics(self, channel_id: int) -> tuple[float, int, float]:
        raise NotImplementedError

    @abstractmethod
    def get_guild_spawn_cooldown_remaining(self, guild_id: int, cooldown_seconds: int) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_guild_spawn_lock(self, guild_id: int) -> asyncio.Lock:
        raise NotImplementedError

    @abstractmethod
    def choose_rock_type(self, channel_id: int) -> constants.RockTierName:
        raise NotImplementedError

    @abstractmethod
    def choose_modifiers(self, rock_type: constants.RockTierName) -> list[constants.Modifier]:
        raise NotImplementedError

    @abstractmethod
    async def notify_spawn_subscribers(
        self,
        guild: discord.Guild,
        settings: GuildSettings,
        destination: t.Callable[[str], t.Awaitable[discord.Message]],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_player_achievements(self, user: discord.User | discord.Member | int) -> list[PlayerAchievement]:
        raise NotImplementedError

    @abstractmethod
    async def get_player_achievement_stats(self, user: discord.User | discord.Member | int) -> PlayerAchievementStats:
        raise NotImplementedError

    @abstractmethod
    async def unlock_player_achievements(
        self,
        user: discord.User | discord.Member | int,
        keys: list[str],
        destination: discord.abc.Messageable | None = None,
        notify: bool = False,
    ) -> list[achievements.AchievementDef]:
        raise NotImplementedError

    @abstractmethod
    async def sync_player_achievements(
        self,
        user: discord.User | discord.Member | int,
        destination: discord.abc.Messageable | None = None,
        notify: bool = False,
    ) -> list[achievements.AchievementDef]:
        raise NotImplementedError

    @abstractmethod
    async def announce_achievement_unlocks(
        self,
        destination: discord.abc.Messageable,
        user: discord.User | discord.Member | int,
        unlocked: list[achievements.AchievementDef],
    ) -> None:
        raise NotImplementedError
