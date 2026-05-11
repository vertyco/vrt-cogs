import typing as t
from abc import ABC, ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from piccolo.engine.postgres import PostgresEngine
from redbot.core.bot import Red

from .common import constants, tracker
from .db.tables import GuildSettings
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
