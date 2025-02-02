import typing as t
from abc import ABC, ABCMeta, abstractmethod

import discord
from discord.ext.commands.cog import CogMeta
from redbot.core import Config
from redbot.core.bot import Red

from .common.api import Result
from .common.models import TranslateButton


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.config: Config

    @abstractmethod
    async def translate(self, msg: str, dest: str, force: bool = False) -> t.Optional[Result]:
        raise NotImplementedError

    @abstractmethod
    async def get_buttons(self, guild: discord.Guild) -> list[TranslateButton]:
        raise NotImplementedError
