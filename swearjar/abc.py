from abc import ABCMeta

from discord.ext.commands.cog import CogMeta
from redbot.core import Config
from redbot.core.bot import Red


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(metaclass=ABCMeta):
    """Type hinting"""

    bot: Red
    config: Config
