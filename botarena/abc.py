import asyncio
from abc import ABC, ABCMeta
from pathlib import Path

from discord.ext.commands.cog import CogMeta
from redbot.core.bot import Red

from .common.models import DB, PartsRegistry
from .common.telemetry import BattleTelemetry


class CompositeMetaClass(CogMeta, ABCMeta):
    """Metaclass for combining Cog and ABC functionality"""


class MixinMeta(ABC):
    """Type hinting mixin for all command classes"""

    def __init__(self, *_args):
        self.bot: Red
        self.db: DB
        self.registry: PartsRegistry
        self.data_path: Path
        self.telemetry: BattleTelemetry
        self.active_battles: set[int]
        self.battle_semaphore: asyncio.Semaphore

    def save(self) -> None:
        raise NotImplementedError
