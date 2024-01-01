from abc import ABC, ABCMeta
from pathlib import Path

from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    bot: Red
    path: Path
