from abc import ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red
from redbot.core.config import Config


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    config: Config

    @abstractmethod
    async def initialize(self, target_guild: discord.Guild = None) -> None:
        raise NotImplementedError
