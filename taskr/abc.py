from abc import ABC, ABCMeta, abstractmethod

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext.commands.cog import CogMeta
from redbot.core import commands
from redbot.core.bot import Red

from .common.models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB
        self.scheduler: AsyncIOScheduler

    @abstractmethod
    def save(self, maybe: bool = False) -> None:
        raise NotImplementedError

    @abstractmethod
    async def is_premium(self, ctx: commands.Context | discord.Guild) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def send_modlog(self, guild: discord.Guild, content: str = None, embed: discord.Embed = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def ensure_jobs(self) -> bool:
        raise NotImplementedError
