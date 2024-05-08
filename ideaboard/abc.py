from abc import ABC, ABCMeta, abstractmethod

import discord
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

    @abstractmethod
    async def save(self) -> None:
        """Save the config"""
        raise NotImplementedError

    @abstractmethod
    async def fetch_profile(self, user: discord.Member) -> discord.Embed:
        """Get the user's profile"""
        raise NotImplementedError
