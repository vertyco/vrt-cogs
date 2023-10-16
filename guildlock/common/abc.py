from abc import ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    db: DB

    @abstractmethod
    def notify_reason(self, log_type: str, guild: discord.Guild) -> str:
        raise NotImplementedError

    @abstractmethod
    def log_reason(self, log_type: str, guild: discord.Guild) -> str:
        raise NotImplementedError

    @abstractmethod
    async def notify_guild(self, log_type: str, guild: discord.Guild):
        raise NotImplementedError

    @abstractmethod
    async def log_leave(self, reason: str, guild: discord.Guild):
        raise NotImplementedError
