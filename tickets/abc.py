from abc import ABC, ABCMeta, abstractmethod
from typing import Dict, List

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red
from redbot.core.config import Config

from .common.models import DB


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.config: Config
        self.db: DB
        self.saving: bool
        self.initialized: bool
        self.valid: List[str]
        self.views: List[discord.ui.View]
        self.view_cache: Dict[int, List[discord.ui.View]]
        self.closing_channels: set[int]

    @abstractmethod
    async def initialize(self, target_guild: discord.Guild = None) -> None:
        raise NotImplementedError

    @abstractmethod
    async def save(self) -> None:
        raise NotImplementedError
