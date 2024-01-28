from abc import ABCMeta, abstractmethod

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
        """Save the config"""
        raise NotImplementedError
