import asyncio
from abc import ABC, ABCMeta, abstractmethod

from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .common.models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB
        self.guild_locks: dict[int, asyncio.Lock]

    @abstractmethod
    def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def sync_automod_rules(self, guild_id: int) -> None:
        raise NotImplementedError
