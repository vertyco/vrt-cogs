from abc import ABC, ABCMeta, abstractmethod

from discord.ext.commands.cog import CogMeta
from piccolo.engine.postgres import PostgresEngine
from piccolo.engine.sqlite import SQLiteEngine
from redbot.core.bot import Red

from .common.utils import DBUtils
from .db.tables import GlobalSettings


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: SQLiteEngine | PostgresEngine | None
        self.db_utils: DBUtils

    @abstractmethod
    async def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def db_active(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def configure_task_intervals(self, settings: GlobalSettings) -> None:
        raise NotImplementedError

    @abstractmethod
    def change_economy_interval(self, minutes: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def change_member_interval(self, minutes: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def change_performance_interval(self, minutes: int) -> None:
        raise NotImplementedError
