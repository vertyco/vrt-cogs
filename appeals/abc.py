import typing as t
from abc import ABC, ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from piccolo.engine.sqlite import SQLiteEngine
from redbot.core.bot import Red

from .db.utils import DBUtils


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: SQLiteEngine | None
        self.db_utils: DBUtils

    @abstractmethod
    async def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def conditions_met(self, guild: discord.Guild) -> t.Tuple[bool, t.Optional[str]]:
        raise NotImplementedError
