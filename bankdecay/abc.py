import typing as t
from abc import ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .common.models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    db: DB

    @abstractmethod
    async def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def decay_guild(self, guild: discord.Guild, check_only: bool = False) -> t.Dict[str, int]:
        raise NotImplementedError
