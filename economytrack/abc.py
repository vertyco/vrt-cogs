from abc import ABC, ABCMeta, abstractmethod
from concurrent.futures import ThreadPoolExecutor

import discord
import pandas as pd
from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red
from redbot.core.config import Config


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""
    bot: Red
    config: Config
    executor: ThreadPoolExecutor

    @abstractmethod
    async def get_plot(self, df: pd.DataFrame) -> discord.File:
        raise NotImplementedError

    @abstractmethod
    async def get_total_bal(self, guild: discord.guild = None) -> int:
        raise NotImplementedError
