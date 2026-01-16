from abc import ABC, ABCMeta, abstractmethod

from discord.ext.commands.cog import CogMeta
from piccolo.engine.postgres import PostgresEngine
from redbot.core.bot import Red

from .common import tracker
from .db.utils import DBUtils


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: PostgresEngine | None
        self.db_utils: DBUtils

        self.activity: tracker.ActivityTracker
        self.active_guild_rocks: dict[int, int]
        self.active_channel_rocks: set[int]

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
