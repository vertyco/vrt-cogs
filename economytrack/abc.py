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
    @staticmethod
    async def get_plot(df: pd.DataFrame, y_label: str) -> discord.File:
        raise NotImplementedError
