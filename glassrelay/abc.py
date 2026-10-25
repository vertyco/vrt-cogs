from abc import ABC, ABCMeta

import aiohttp
from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .db.database import Database


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: Database
        self.session: aiohttp.ClientSession
