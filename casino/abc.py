import asyncio
import random
import typing as t
from abc import ABC, ABCMeta, abstractmethod

from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .common.money import Money, RedBank
from .common.store import Store
from .common.table import Floor


class CompositeMetaClass(CogMeta, ABCMeta):
    """Type detection"""


class MixinMeta(ABC):
    """Type hinting"""

    def __init__(self, *args):
        self.bot: Red
        self.store: Store
        self.bank: RedBank
        self.money: Money
        self.rng: random.Random
        self.table_types: dict
        self.floors: dict[str, Floor]
        self.ready: asyncio.Event
        self.play_view: t.Any

    @abstractmethod
    async def send_me(self, floor: Floor, member) -> None: ...

    @abstractmethod
    async def refresh(self, scope: int | None = None) -> None: ...

    @abstractmethod
    def floor_done(self, floor: Floor) -> None: ...
