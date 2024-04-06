import typing as t
from abc import ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core import commands
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
    async def cost_check(self, ctx: t.Union[commands.Context, discord.Interaction]):
        raise NotImplementedError
