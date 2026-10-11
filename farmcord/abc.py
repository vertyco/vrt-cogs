import asyncio
import random
import typing as t
from abc import ABC, ABCMeta

from discord.ext.commands.cog import CogMeta
from redbot.core import Config
from redbot.core.bot import Red

from .common.payouts import Payouts
from .common.store import Store


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *args):
        self.bot: Red
        self.store: Store
        self.config: Config
        self.payouts: Payouts
        self.clock: t.Callable[[], float]
        self.rng: random.Random
        self.ready: asyncio.Event
        self.locks: dict[int, asyncio.Lock]
        self.play_view: t.Any
